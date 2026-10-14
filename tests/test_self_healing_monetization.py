--- a/atlas/nn/modules.py
+++ b/atlas/nn/modules.py
@@ -123,7 +123,7 @@
 class MultiScaleDeformableAttention(Module):
     def __init__(self, d_model: int, n_levels: int, n_heads: int, n_points: int):
-        if d_model % 32 != 0:
+        if d_model % 16 != 0:
             raise ValueError("d_model must be a multiple of 16")
         super().__init__()
         self.d_model = d_model
         self.n_levels = n_levels
