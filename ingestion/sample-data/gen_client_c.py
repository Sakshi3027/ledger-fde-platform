import sys
sys.path.insert(0, '.')
import generate_claims
import csv

generate_claims.random.seed(99)
claims = [generate_claims.generate_claim(i) for i in range(1, 51)]
claims = generate_claims.inject_curveball_cases(claims)
generate_claims.random.shuffle(claims)

with open('claims_client_c.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=claims[0].keys())
    writer.writeheader()
    writer.writerows(claims)

print(f'generated {len(claims)} claims -> claims_client_c.csv')
