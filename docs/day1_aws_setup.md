# Day 1 — AWS Setup

## What I Did

I created an AWS account, set up a secure IAM user with S3 permissions, generated
access keys, and created the S3 bucket that the pipeline writes raw data to.

---

## Core Concepts

### What AWS is

Amazon Web Services is a cloud platform — a collection of infrastructure services you
rent instead of owning. Instead of buying a server, you rent compute time. Instead of
buying storage hardware, you rent object storage (S3).

For this project we're only using one AWS service: **S3 (Simple Storage Service)**.
S3 is object storage — you store files (called "objects") in buckets. There's no folder
hierarchy, just a bucket name and a key (the full path of the file, like
`mko/raw/product/2026-04-24/products.parquet`). The slash-separated paths look like
folders but S3 treats them as one long filename.

**Why S3 and not Google Drive or Dropbox?**
S3 is the industry standard for data engineering. It integrates natively with
essentially every data tool (DuckDB, Spark, dbt, Airflow). It's designed for
programmatic access, not human file browsing. Google Drive is designed for humans
sharing documents — its API is awkward for data pipelines.

---

### What IAM is

IAM (Identity and Access Management) is AWS's permission system. Every action in AWS
(uploading a file, reading a file, creating a bucket) requires an identity with the
right permissions.

There are two types of identity relevant here:

**Root account** — the email/password you used to sign up for AWS. This identity has
unlimited access to everything including billing and account deletion. You should
almost never use this for day-to-day work. If those credentials leaked, someone could
delete your entire account or run up a huge bill.

**IAM users** — separate identities you create within your account, each with specific
permissions. I created `supply-integration-local` with access only to S3.

This is the principle of **least privilege**: give each identity only the permissions
it needs and nothing more. Our pipeline only needs to read and write S3 — it doesn't
need to create EC2 instances or modify billing settings.

---

### What access keys are

When a human logs into AWS, they use a username and password via the browser.
When code (like our Python pipeline) talks to AWS, it uses an **access key pair**:

- **Access Key ID** — like a username. Not secret. Identifies which IAM user is making
  the request.
- **Secret Access Key** — like a password. Secret. Used to cryptographically sign
  requests so AWS knows they're authentic.

Together they let our Python code say to AWS: "I am `supply-integration-local`,
here's proof, please let me upload this file to the supply-integration bucket."

boto3 (the AWS Python SDK) automatically looks for these in environment variables:
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. We set these in the `.env` file so
they're available to the pipeline without being in the code.

**Why you only see the Secret Access Key once:** AWS never stores your secret key
after showing it to you. If you lose it, you can't recover it — you can only revoke
the key pair and generate a new one. This is intentional: it forces you to store it
securely rather than assuming you can always retrieve it from AWS.

---

### What an S3 bucket is

A bucket is a top-level container for objects in S3. Bucket names are globally unique
across all AWS accounts — if someone else has already created `supply-integration`,
you can't use that name. Buckets have a region (the physical data centre location
where your data is stored).

I used **eu-south-2 (Europe/Spain)** because:
- Data stays in the EU (relevant for GDPR and personal data considerations)
- Closer to where you're running the pipeline (lower latency)
- You wanted to learn a new region not used at Helloprint

One gotcha we hit: DuckDB's httpfs extension doesn't automatically resolve newer AWS
regions. We had to explicitly set `s3_endpoint: s3.eu-south-2.amazonaws.com` in
profiles.yml. This was an unexpected learning — newer AWS regions sometimes require
explicit endpoint configuration in tools that aren't kept up to date.

---

## What I Set Up

### IAM user creation

1. Searched for IAM in the AWS Console
2. Created user `supply-integration-local`
3. Did **not** tick "Provide user access to the AWS Management Console" — this user
   is for code, not for a human logging into the browser
4. Attached the `AmazonS3FullAccess` policy directly

`AmazonS3FullAccess` gives the user permission to read and write any S3 bucket in
the account. For a personal project this is fine. In a production environment you'd
write a custom policy that only allows access to the specific bucket:

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::supply-integration",
    "arn:aws:s3:::supply-integration/*"
  ]
}
```

### Access key generation

1. Opened the IAM user → Security credentials tab
2. Created access key, selected "Local code" as the use case
3. AWS showed a warning recommending IAM Identity Center instead — this is the
   enterprise approach for teams. For a personal project, static access keys are fine.
4. Copied both the Access Key ID and Secret Access Key immediately

### S3 bucket creation

1. Searched for S3 in the console
2. Created bucket `supply-integration` in region `eu-south-2`
3. Left all defaults — no public access, no versioning (not needed for this project)

### .env file

Added the credentials to `.env`:
```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=eu-south-2
S3_BUCKET=supply-integration
```

The `.gitignore` already listed `.env` so these credentials are never committed
to git.

---

## Issues We Hit

### Issue 1: "Provide console access" was ticked by default

**What happened:** The IAM user creation screen had "Provide user access to the AWS
Management Console" pre-ticked. This adds unnecessary complexity (a console password,
a login URL) for a user that only needs programmatic access.

**Fix:** Unticked it. The user only needs access keys, not a console login.

**Lesson:** AWS console defaults are often set for the most common human-facing use
case. When creating service/programmatic users, check what's pre-ticked.

### Issue 2: Token pasted as username in git push

**What happened:** When git prompted for a GitHub username and password, the Personal
Access Token was pasted into the username field instead of the password field.

**Fix:** Revoked the exposed token immediately in GitHub settings and generated a new one.

**Lesson:** Treat tokens and credentials like passwords. If one is ever exposed (in a
terminal, a chat, a log file, a GitHub commit), revoke it immediately and generate a
new one. The cost of revoking a token is low; the cost of an exposed credential is high.

---

## What You Should Be Able to Explain After Day 1

- What S3 is and how it differs from a traditional filesystem
- Why you use an IAM user instead of your root account
- What the principle of least privilege means
- What an access key pair is and how boto3 uses it
- Why the Secret Access Key is only shown once
- Why credentials go in `.env` and not in code or git
- What a bucket region means and why you chose eu-south-2
