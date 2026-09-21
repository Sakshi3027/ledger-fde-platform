"""
Synthetic claims generator, schema grounded in CMS's DE-SynPUF
(Data Entrepreneurs' Synthetic Public Use File) conventions —
the real public dataset CMS publishes for building/testing
claims systems without touching real patient data.
https://www.cms.gov/data-research/statistics-trends-reports/medicare-claims-synthetic-public-use-files
"""

import csv
import random
import string
from datetime import date, timedelta

random.seed(42)  # reproducible output

# Real HCPCS/CPT procedure codes, common outpatient/carrier claims
PROCEDURE_CODES = [
    "99213",  # office visit, established patient
    "99214",  # office visit, moderate complexity
    "71020",  # chest X-ray
    "80053",  # comprehensive metabolic panel
    "93000",  # EKG
    "36415",  # blood draw
    "97110",  # therapeutic exercise
    "99396",  # preventive visit, 40-64 years
]

# Real ICD-9 diagnosis codes (DE-SynPUF predates ICD-10 adoption)
DIAGNOSIS_CODES = [
    "4019",   # hypertension
    "25000",  # diabetes mellitus type 2
    "4280",   # congestive heart failure
    "V700",   # routine general exam
    "7242",   # lumbago (back pain)
    "3659",   # glaucoma
    "78650",  # chest pain
]

# CMS provider specialty codes
SPECIALTIES = ["01", "11", "20", "38", "93"]  # general practice, internal med, cardiology, etc.

CLAIM_TYPES = ["Carrier", "Outpatient", "Inpatient"]

def random_desynpuf_id():
    # DE-SynPUF's actual patient ID format: alphanumeric, 16 chars
    return ''.join(random.choices(string.digits + string.ascii_uppercase, k=16))

def random_npi():
    # NPI (National Provider Identifier) is a real 10-digit number
    return ''.join(random.choices(string.digits, k=10))

def random_date():
    start = date(2026, 1, 1)
    offset = random.randint(0, 180)
    return (start + timedelta(days=offset)).isoformat()

def generate_claim(claim_num):
    procedure = random.choice(PROCEDURE_CODES)
    base_amount = {
        "99213": 110, "99214": 165, "71020": 85, "80053": 45,
        "93000": 60, "36415": 15, "97110": 55, "99396": 195,
    }.get(procedure, 100)

    return {
        "claim_id": f"CLM{claim_num:08d}",
        "desynpuf_id": random_desynpuf_id(),
        "provider_id": random_npi(),
        "provider_specialty": random.choice(SPECIALTIES),
        "procedure_code": procedure,
        "diagnosis_code": random.choice(DIAGNOSIS_CODES),
        "claim_type": random.choice(CLAIM_TYPES),
        "billed_amount": round(base_amount * random.uniform(0.85, 1.4), 2),
        "submitted_date": random_date(),
    }

def inject_curveball_cases(claims):
    """
    Deliberately inject known-bad records the rules engine
    should catch — this is what makes the dataset useful for
    actually testing the rules engine, not just populating it.
    """
    # Case 1: billed amount way above normal for the procedure (overbilling flag)
    outlier = generate_claim(9001)
    outlier["procedure_code"] = "99213"
    outlier["billed_amount"] = 850.00  # ~8x normal for this code
    claims.append(outlier)

    # Case 2: duplicate billing — same patient, same procedure, same day
    dup_patient = random_desynpuf_id()
    dup_date = random_date()
    for i in range(2):
        dup = generate_claim(9010 + i)
        dup["desynpuf_id"] = dup_patient
        dup["procedure_code"] = "99214"
        dup["submitted_date"] = dup_date
        claims.append(dup)

    # Case 3: implausible diagnosis/procedure pairing (glaucoma code + EKG procedure)
    mismatch = generate_claim(9020)
    mismatch["procedure_code"] = "93000"  # EKG
    mismatch["diagnosis_code"] = "3659"   # glaucoma — no clinical link
    claims.append(mismatch)

    return claims

def main():
    claims = [generate_claim(i) for i in range(1, 201)]  # 200 normal claims
    claims = inject_curveball_cases(claims)
    random.shuffle(claims)

    with open("claims_client_a.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=claims[0].keys())
        writer.writeheader()
        writer.writerows(claims)

    print(f"generated {len(claims)} claims -> claims_client_a.csv")
    print("includes 4 deliberately injected exception cases for rules engine testing")

if __name__ == "__main__":
    main()
