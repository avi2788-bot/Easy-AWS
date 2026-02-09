# EasyAWS CLI ☁️

**EasyAWS** is a lightweight, safety-first Python CLI for provisioning and managing AWS resources. It is designed with built-in guardrails to prevent accidental over-provisioning and ensures that it only creates, modifies, or deletes resources specifically tagged by this tool.

## 🚀 Features

* **EC2 Manager:** Launch instances (auto-fetches latest AMIs), list, start, and stop.
    * *Guardrails:* Restricts instance types to `t3.micro`/`t2.small` and enforces a hard cap of **2 running instances**.
* **S3 Manager:** Create buckets (private or public), list, and upload files.
* **Route53 Manager:** Create hosted zones and manage 'A' records.
* **Safety Tagging:** All resources are automatically tagged with `CreatedBy: easy-aws` and `Owner: <your-username>`. Operations are refused on resources missing these tags.
* **Global Cleanup:** A "Nuke" feature to tear down all resources created by this tool in one command.

## 📋 Prerequisites

1.  **Python 3.6+**
2.  **AWS Credentials** configured locally (via AWS CLI or Environment Variables).
    * Run `aws configure` to set up your keys.

## 🛠️ Installation

1.  Clone this repository or save the script as `easy_aws.py`.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Make the script executable (optional):
    ```bash
    chmod +x easy_aws.py
    ```

## 📖 Usage

### EC2 (Compute)

*Supports Amazon Linux 2 (default) and Ubuntu 20.04.*

**Launch an Instance:**
```bash
# Default (Amazon Linux 2, t3.micro)
python3 easy_aws.py ec2 create

# Custom OS and Type
python3 easy_aws.py ec2 create --os ubuntu --type t2.small
```

**Manage Instances:**
```bash
# List all EasyAWS instances
python3 easy_aws.py ec2 list

# Stop an instance
python3 easy_aws.py ec2 stop --id i-0123456789abcdef0

# Start an instance
python3 easy_aws.py ec2 start --id i-0123456789abcdef0
```

---

### S3 (Storage)

**Create a Bucket:**
```bash
# Create a private bucket (default)
python3 easy_aws.py s3 create --name my-unique-bucket-name-123

# Create a public bucket (requires interactive confirmation)
python3 easy_aws.py s3 create --name my-public-bucket-123 --public
```

**Upload & List:**
```bash
# Upload a file
python3 easy_aws.py s3 upload --name my-unique-bucket-name-123 --file ./hello.txt

# List buckets created by this tool
python3 easy_aws.py s3 list
```

---

### Route53 (DNS)

**Manage Zones & Records:**
```bash
# Create a Hosted Zone
python3 easy_aws.py r53 create-zone --domain example.com

# List Zones
python3 easy_aws.py r53 list

# Upsert an 'A' Record
python3 easy_aws.py r53 manage-record --zone-id Z123456789 --record app.example.com --value 192.168.1.1
```

---

## ⚠️ Cleanup (The "Nuke" Button)

This command will recursively find **ALL** resources tagged with `CreatedBy: easy-aws` and destroy them.

* Terminates EC2 instances.
* Empties and deletes S3 buckets.
* Deletes Route53 records and Hosted Zones.

```bash
python3 easy_aws.py cleanup
```

> **⚠️ Warning:** You will be prompted to type `DELETE` to confirm.

---

## 🛡️ Guardrails & Security

To prevent accidents and high costs:

| Guardrail | Description |
|-----------|-------------|
| **Instance Cap** | The script checks for running instances before launching. If you have 2 running instances tagged `easy-aws`, creation is denied. |
| **Type Restriction** | Only `t3.micro` and `t2.small` are allowed. |
| **Ownership Check** | The script checks tags before stopping instances, deleting buckets, or updating DNS. It will not touch resources created manually via the AWS Console or other tools. |
