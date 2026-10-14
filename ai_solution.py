```python
import google.cloud.billing

def check_gcp_billing():
    billing = google.cloud.billing.BillingV1().projects()
    project_billing = {}
    for project in billing.list_billing_projects():
        project_billing[project['name']] = project.get('billingEnabled', False)
    return f"GCP facturation activée pour le projet test-bot-499814 ? {project_billing.get('test-bot-499814', False)}."
```