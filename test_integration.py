"""
Quick integration test — verifies the full evaluation pipeline
with a mock architecture (no LLM needed).
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config import THRESHOLDS
from prompt.builder import build_architecture_prompt
from parsing.parser import parse_architecture
from evaluation import evaluate_architecture
from evaluation.cas import rank_candidates
from output.report import generate_report
from output.plantuml_gen import generate_plantuml
from output.mermaid_gen import generate_mermaid
from output.radar import generate_radar_chart

# Load sample input
with open("input/sample_food_delivery.json", "r") as f:
    requirements = json.load(f)

# Mock architecture (simulating what an LLM would produce)
mock_arch = {
    "architecture_style": "Microservices",
    "layers": [
        {"name": "Presentation", "order": 1},
        {"name": "API Gateway", "order": 2},
        {"name": "Business Logic", "order": 3},
        {"name": "Data Access", "order": 4},
        {"name": "Infrastructure", "order": 5}
    ],
    "components": [
        {"name": "WebAppController", "layer": "Presentation", "responsibility": "Handles user interface rendering and client-side interactions for customers"},
        {"name": "MobileAppController", "layer": "Presentation", "responsibility": "Manages mobile application views and push notification display"},
        {"name": "APIGatewayService", "layer": "API Gateway", "responsibility": "Routes incoming API requests and handles authentication and rate limiting"},
        {"name": "OrderService", "layer": "Business Logic", "responsibility": "Manages order creation validation lifecycle tracking and status updates"},
        {"name": "PaymentService", "layer": "Business Logic", "responsibility": "Processes secure payment transactions with encryption and fraud detection"},
        {"name": "DeliveryTrackingService", "layer": "Business Logic", "responsibility": "Tracks delivery driver location in real time on map"},
        {"name": "RestaurantService", "layer": "Business Logic", "responsibility": "Manages restaurant profiles menu items and pricing information"},
        {"name": "NotificationService", "layer": "Business Logic", "responsibility": "Sends push notifications emails and SMS for order status changes"},
        {"name": "UserManagementService", "layer": "Business Logic", "responsibility": "Handles user registration authentication and admin management of users"},
        {"name": "ReviewRatingService", "layer": "Business Logic", "responsibility": "Manages customer reviews and ratings for restaurants and drivers"},
        {"name": "DriverService", "layer": "Business Logic", "responsibility": "Manages driver profiles delivery acceptance and completion workflows"},
        {"name": "OrderRepository", "layer": "Data Access", "responsibility": "Provides data access operations for order persistence and retrieval"},
        {"name": "UserRepository", "layer": "Data Access", "responsibility": "Handles database operations for user and driver data storage"},
        {"name": "CacheManager", "layer": "Infrastructure", "responsibility": "Redis-based caching layer for performance optimization of frequent queries"},
        {"name": "LoadBalancerProxy", "layer": "Infrastructure", "responsibility": "Distributes incoming traffic across multiple service instances for scalability"},
        {"name": "MessageBrokerService", "layer": "Infrastructure", "responsibility": "RabbitMQ message queue for async event-driven communication between services"}
    ],
    "interactions": [
        {"from": "WebAppController", "to": "APIGatewayService", "type": "REST", "direction": "down"},
        {"from": "MobileAppController", "to": "APIGatewayService", "type": "REST", "direction": "down"},
        {"from": "APIGatewayService", "to": "OrderService", "type": "REST", "direction": "down"},
        {"from": "APIGatewayService", "to": "UserManagementService", "type": "REST", "direction": "down"},
        {"from": "APIGatewayService", "to": "RestaurantService", "type": "REST", "direction": "down"},
        {"from": "OrderService", "to": "PaymentService", "type": "REST", "direction": "lateral"},
        {"from": "OrderService", "to": "NotificationService", "type": "Event", "direction": "lateral"},
        {"from": "OrderService", "to": "DeliveryTrackingService", "type": "Event", "direction": "lateral"},
        {"from": "OrderService", "to": "OrderRepository", "type": "Direct Call", "direction": "down"},
        {"from": "UserManagementService", "to": "UserRepository", "type": "Direct Call", "direction": "down"},
        {"from": "DeliveryTrackingService", "to": "DriverService", "type": "REST", "direction": "lateral"},
        {"from": "OrderService", "to": "CacheManager", "type": "Direct Call", "direction": "down"},
        {"from": "NotificationService", "to": "MessageBrokerService", "type": "Message Queue", "direction": "down"}
    ]
}

print("=" * 60)
print("INTEGRATION TEST — Mock Architecture Evaluation")
print("=" * 60)

# Test prompt builder
prompt = build_architecture_prompt(requirements)
print(f"\n✅ Prompt built: {len(prompt)} chars")

# Test evaluation
scores = evaluate_architecture(mock_arch, requirements)
print(f"\n📊 EVALUATION RESULTS:")
print(f"   RCR  = {scores['RCR']:.4f}  (threshold: {THRESHOLDS['RCR']})")
print(f"   NAS  = {scores['NAS']:.4f}  (threshold: {THRESHOLDS['NAS']})")
print(f"   SMI  = {scores['SMI']:.4f}  (threshold: {THRESHOLDS['SMI']})")
print(f"   LSCS = {scores['LSCS']:.4f}  (threshold: {THRESHOLDS['LSCS']})")
print(f"   SCI  = {scores['SCI']:.4f}  (threshold: {THRESHOLDS['SCI']})")
print(f"   ─────────────────────")
print(f"   CAS  = {scores['CAS']:.4f}  (threshold: {THRESHOLDS['CAS']})")
print(f"   Verdict: {scores['verdict']}")

# Test ranking with 2 mock candidates
candidates = [
    {"model": "llama3.1", "candidate_num": 1, "architecture": mock_arch, "scores": scores},
    {"model": "mistral", "candidate_num": 1, "architecture": mock_arch,
     "scores": {**scores, "CAS": scores["CAS"] - 0.05, "RCR": scores["RCR"] - 0.1}},
]
ranked = rank_candidates(candidates)
print(f"\n🏆 Ranking: {[(c['rank'], c['model'], c['scores']['CAS']) for c in ranked]}")

# Test output generators
report = generate_report(ranked, requirements, "TEST01")
print(f"\n✅ Report generated: {len(report)} chars")

puml = generate_plantuml(mock_arch, "Food Delivery")
print(f"✅ PlantUML generated: {len(puml)} chars")

mmd = generate_mermaid(mock_arch, "Food Delivery")
print(f"✅ Mermaid generated: {len(mmd)} chars")

# Test radar chart
from config import RESULTS_DIR
radar_path = str(RESULTS_DIR / "test_radar.png")
generate_radar_chart(ranked, radar_path, "Test Radar")
print(f"✅ Radar chart saved: {radar_path}")

print(f"\n{'=' * 60}")
print("ALL INTEGRATION TESTS PASSED ✅")
print(f"{'=' * 60}")
