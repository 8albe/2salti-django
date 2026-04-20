import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from matches.services.ocr_service import (
    normalize_name, normalize_team_name, simple_similarity, 
    resolve_entity, resolve_team_entity, resolve_athlete
)
from dataclasses import dataclass

@dataclass
class MockObj:
    name: str

def test_normalization():
    print("Testing base normalization...")
    cases = [
        ("Pro Recco v", "pro recco"),
        ("Brescia g", "brescia"),
        ("Test x", "test"),
        ("  Multiple  Spaces  ", "multiple spaces"),
    ]
    for input_name, expected in cases:
        result = normalize_name(input_name)
        print(f"  '{input_name}' -> '{result}' | {'PASS' if result == expected else 'FAIL'}")

def test_team_normalization():
    print("\nTesting team-specific normalization...")
    cases = [
        ("AN Brescia", "brescia"),
        ("ASD Bogliasco", "bogliasco"),
        ("SS Lazio", "lazio"),
        ("Soc Pro Recco", "pro recco"),
    ]
    for input_name, expected in cases:
        result = normalize_team_name(input_name)
        print(f"  '{input_name}' -> '{result}' | {'PASS' if result == expected else 'FAIL'}")

def test_athlete_resolution():
    print("\nTesting athlete-specific resolution pipeline...")
    queryset = [
        MockObj(name="Marco Rossi"),
        MockObj(name="Athlete B"),
        # Ambiguity case
        MockObj(name="Luca Rossi"),
        MockObj(name="Luca Bianchi"),
    ]

    cases = [
        ("Rossi Marco", "Marco Rossi", "Token Match (Inversion)"),
        ("AthB", "Athlete B", "Initial Match (Abbreviation)"),
        ("Marco Rossu", "Marco Rossi", "Fuzzy Match (Fallback)"),
        ("Luca", None, "Ambiguity safety (multiple Luca)"),
        ("Nobody", None, "No match"),
    ]

    for input_name, expected_obj_name, label in cases:
        result = resolve_athlete(input_name, queryset)
        result_name = result.name if result else None
        print(f"  [{label}] '{input_name}' -> '{result_name}' | {'PASS' if result_name == expected_obj_name else 'FAIL'}")

def test_collision_safety():
    print("\nTesting collision safety...")
    queryset = [
        MockObj(name="Andrea Rossi"),
        MockObj(name="Andrea Verdi"),
    ]
    # "Andrea" should NOT match neither if both are present
    result = resolve_athlete("Andrea", queryset)
    print(f"  'Andrea' vs Multiple -> {result.name if result else 'None'} | {'PASS' if result is None else 'FAIL'}")

if __name__ == "__main__":
    test_normalization()
    test_team_normalization()
    test_athlete_resolution()
    test_collision_safety()
