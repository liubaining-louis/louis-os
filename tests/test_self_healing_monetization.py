--- a/atlas/strategic_decision.py
+++ b/atlas/strategic_decision.py
@@ -51,7 +51,7 @@
     value: float = 0.7,
     confidence: float = 0.8,
     effort: int = 2,
     token_cost: int = 1000,
-    monetary_cost: float = 0.0,
+    monetary_cost: float = 2500.0,  # updated to match the bounty reward
     reversibility: float = 1.0,
     information_gain: float = 0.5,
     risk: int = 1,
