package com.ledger.rediscache;

import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

public class App {
    private static final int PORT = 6380;
    private static final String AOF_FILE = "redis-java.aof";

    private static final int MAX_ENTRIES = 1000;

    // LinkedHashMap in access-order mode gives us LRU eviction almost for free:
    // every get() or put() moves that key to the "most recently used" end,
    // so the eldest entry is always the least recently used one.
    private static final Map<String, String> store = Collections.synchronizedMap(
        new LinkedHashMap<String, String>(16, 0.75f, true) {
            protected boolean removeEldestEntry(Map.Entry<String, String> eldest) {
                boolean shouldEvict = size() > MAX_ENTRIES;
                if (shouldEvict) {
                    System.out.println("evicting key (LRU): " + eldest.getKey());
                }
                return shouldEvict;
            }
        }
    );
    private static final Map<String, Long> expiry = new ConcurrentHashMap<>();
    private static final Map<String, Map<String, String>> hashStore = new ConcurrentHashMap<>();

    private static PrintWriter aofWriter;

    public static void main(String[] args) throws IOException {
        loadAof();
        openAofWriter();

        ServerSocket serverSocket = new ServerSocket(PORT);
        System.out.println("redis-java listening on port " + PORT);

        while (true) {
            Socket clientSocket = serverSocket.accept();
            Thread clientThread = new Thread(() -> handleClient(clientSocket));
            clientThread.start();
        }
    }

    // Replays the AOF file on startup, rebuilding in-memory state from the write log.
    private static void loadAof() throws IOException {
        Path path = Paths.get(AOF_FILE);
        if (!Files.exists(path)) {
            System.out.println("no AOF file found, starting with empty store");
            return;
        }

        int replayed = 0;
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) continue;
                List<String> command = splitAofLine(line);
                execute(command); // replay: re-run the command against the in-memory store
                replayed++;
            }
        }
        System.out.println("replayed " + replayed + " commands from AOF");
    }

    // AOF lines are stored as tab-separated args, e.g. "SET\tfoo\tbar"
    private static List<String> splitAofLine(String line) {
        return new ArrayList<>(Arrays.asList(line.split("\t")));
    }

    private static void openAofWriter() throws IOException {
        aofWriter = new PrintWriter(new FileWriter(AOF_FILE, true)); // true = append mode
    }

    // Called after every successful mutating command to persist it.
    private static void appendToAof(List<String> command) {
        synchronized (aofWriter) {
            aofWriter.println(String.join("\t", command));
            aofWriter.flush(); // flush immediately so we don't lose writes on a crash
        }
    }

    private static void handleClient(Socket clientSocket) {
        try (
            InputStream rawIn = clientSocket.getInputStream();
            BufferedReader in = new BufferedReader(new InputStreamReader(rawIn));
            OutputStream out = clientSocket.getOutputStream()
        ) {
            while (true) {
                List<String> command = parseResp(in);
                if (command == null) break;
                if (command.isEmpty()) continue;

                String reply = execute(command);

                if (isMutatingCommand(command.get(0))) {
                    appendToAof(command);
                }

                out.write(reply.getBytes());
                out.flush();
            }
        } catch (IOException e) {
            System.err.println("client error: " + e.getMessage());
        } finally {
            try {
                clientSocket.close();
            } catch (IOException e) {
                // ignore
            }
        }
    }

    private static boolean isMutatingCommand(String cmd) {
        switch (cmd.toUpperCase()) {
            case "SET": case "DEL": case "EXPIRE": case "HSET": case "HDEL":
                return true;
            default:
                return false;
        }
    }

    private static List<String> parseResp(BufferedReader in) throws IOException {
        String line = in.readLine();
        if (line == null) return null;

        if (!line.startsWith("*")) {
            return Collections.emptyList();
        }

        int numArgs = Integer.parseInt(line.substring(1).trim());
        List<String> args = new ArrayList<>();

        for (int i = 0; i < numArgs; i++) {
            String lenLine = in.readLine();
            if (lenLine == null || !lenLine.startsWith("$")) {
                return Collections.emptyList();
            }
            int len = Integer.parseInt(lenLine.substring(1).trim());
            char[] buf = new char[len];
            int read = 0;
            while (read < len) {
                int r = in.read(buf, read, len - read);
                if (r == -1) return null;
                read += r;
            }
            in.readLine();
            args.add(new String(buf));
        }

        return args;
    }

    private static String execute(List<String> command) {
        String cmd = command.get(0).toUpperCase();

        switch (cmd) {
            case "PING":
                return "+PONG\r\n";

            case "SET": {
                if (command.size() < 3) return "-ERR wrong number of arguments for SET\r\n";
                String key = command.get(1);
                String value = command.get(2);
                store.put(key, value);
                expiry.remove(key);
                return "+OK\r\n";
            }

            case "GET": {
                if (command.size() < 2) return "-ERR wrong number of arguments for GET\r\n";
                String key = command.get(1);
                if (isExpired(key)) {
                    store.remove(key);
                    expiry.remove(key);
                }
                String value = store.get(key);
                if (value == null) return "$-1\r\n";
                return "$" + value.length() + "\r\n" + value + "\r\n";
            }

            case "DEL": {
                if (command.size() < 2) return "-ERR wrong number of arguments for DEL\r\n";
                int deleted = 0;
                for (int i = 1; i < command.size(); i++) {
                    String key = command.get(i);
                    if (store.remove(key) != null) deleted++;
                    if (hashStore.remove(key) != null) deleted++;
                    expiry.remove(key);
                }
                return ":" + deleted + "\r\n";
            }

            case "EXPIRE": {
                if (command.size() < 3) return "-ERR wrong number of arguments for EXPIRE\r\n";
                String key = command.get(1);
                if (!store.containsKey(key) && !hashStore.containsKey(key)) return ":0\r\n";
                long seconds = Long.parseLong(command.get(2));
                expiry.put(key, System.currentTimeMillis() + (seconds * 1000));
                return ":1\r\n";
            }

            case "HSET": {
                if (command.size() < 4) return "-ERR wrong number of arguments for HSET\r\n";
                String key = command.get(1);
                String field = command.get(2);
                String value = command.get(3);
                hashStore.computeIfAbsent(key, k -> new ConcurrentHashMap<>()).put(field, value);
                return ":1\r\n";
            }

            case "HGET": {
                if (command.size() < 3) return "-ERR wrong number of arguments for HGET\r\n";
                String key = command.get(1);
                String field = command.get(2);
                Map<String, String> h = hashStore.get(key);
                if (h == null || !h.containsKey(field)) return "$-1\r\n";
                String value = h.get(field);
                return "$" + value.length() + "\r\n" + value + "\r\n";
            }

            case "HGETALL": {
                if (command.size() < 2) return "-ERR wrong number of arguments for HGETALL\r\n";
                String key = command.get(1);
                Map<String, String> h = hashStore.get(key);
                if (h == null || h.isEmpty()) return "*0\r\n";

                StringBuilder sb = new StringBuilder();
                sb.append("*").append(h.size() * 2).append("\r\n");
                for (Map.Entry<String, String> entry : h.entrySet()) {
                    sb.append("$").append(entry.getKey().length()).append("\r\n").append(entry.getKey()).append("\r\n");
                    sb.append("$").append(entry.getValue().length()).append("\r\n").append(entry.getValue()).append("\r\n");
                }
                return sb.toString();
            }

            case "HDEL": {
                if (command.size() < 3) return "-ERR wrong number of arguments for HDEL\r\n";
                String key = command.get(1);
                String field = command.get(2);
                Map<String, String> h = hashStore.get(key);
                if (h == null) return ":0\r\n";
                boolean removed = h.remove(field) != null;
                return removed ? ":1\r\n" : ":0\r\n";
            }

            default:
                return "-ERR unknown command '" + cmd + "'\r\n";
        }
    }

    private static boolean isExpired(String key) {
        Long exp = expiry.get(key);
        return exp != null && System.currentTimeMillis() > exp;
    }
}
