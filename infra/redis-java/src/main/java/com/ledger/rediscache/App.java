package com.ledger.rediscache;

import java.io.*;
import java.net.*;

public class App {
    private static final int PORT = 6380; // not 6379, so it never collides with a real Redis if one's running

    public static void main(String[] args) throws IOException {
        ServerSocket serverSocket = new ServerSocket(PORT);
        System.out.println("redis-java listening on port " + PORT);

        while (true) {
            Socket clientSocket = serverSocket.accept();
            handleClient(clientSocket);
        }
    }

    private static void handleClient(Socket clientSocket) {
        try (
            BufferedReader in = new BufferedReader(new InputStreamReader(clientSocket.getInputStream()));
            OutputStream out = clientSocket.getOutputStream()
        ) {
            String line;
            while ((line = in.readLine()) != null) {
                System.out.println("received: " + line);
                if (line.trim().equalsIgnoreCase("PING")) {
                    out.write("+PONG\r\n".getBytes());
                    out.flush();
                }
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
}
