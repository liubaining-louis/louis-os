--- a/atlas/ttnn.py
+++ b/atlas/ttnn.py
@@ -123,7 +123,7 @@
     def div(self, other):
-        return self.val / other.val
+        return self.val / (other.val or 1)
