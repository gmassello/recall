---
name: recall-bootstrap-aws
description: >
  Prepare an AWS account and a GitHub repo so the recall Deploy workflow can run: the GitHub OIDC
  provider, the deploy role and its trust policy, and the repo secrets and variables. Covers the
  immutable `sub` claim that makes hand-written trust policies fail, and how to create the stack
  from the console when there are no CLI credentials. Use it to set this up in a new account or
  repo, or when the role stops being assumable.
allowed-tools: Bash, Read, Grep, Glob
---

# Bootstrapping AWS for the Deploy workflow

One-time setup. It is already done for account 236058984017 / `gmassello/recall`; this is the recipe
for repeating it, and the reference for fixing the trust policy when it breaks.

## What gets created

`infra/github-oidc.yaml` is a CloudFormation template, deliberately a **separate stack** from the app
(`recall-github-oidc` vs `recall`) because its lifecycle is different — created once, untouched by
deploys. It declares:

- `AWS::IAM::OIDCProvider` for `token.actions.githubusercontent.com`, audience `sts.amazonaws.com`.
  `ThumbprintList` is intentionally omitted: it is optional, IAM resolves the CA thumbprint itself,
  and a hardcoded one rots the day GitHub rotates its certificate.
- `AWS::IAM::Role` named `recall-github-deploy`, trusting only the `sub` in the `GitHubSubject`
  parameter, with `PowerUserAccess` plus an inline IAM policy scoped to
  `arn:aws:iam::<account>:role/recall-*`. That inline policy is required: PowerUser excludes IAM, and
  `deploy.sh` passes `--capabilities CAPABILITY_IAM` because SAM creates the Lambda execution role.

`Ref` on the OIDC provider returns its ARN, which is what the role's `Principal.Federated` needs.

## Get the `sub` claim right — this is the trap

GitHub does not necessarily mint `repo:owner/name:ref:refs/heads/main`. It can mint **immutable
IDs**:

```
repo:gmassello@12966514/recall@1306083059:ref:refs/heads/main
```

A trust policy written from the repo *name* then fails with `Not authorized to perform
sts:AssumeRoleWithWebIdentity`, and the message says nothing about why.

Do not compose the value by hand. Get the IDs:

```bash
gh api repos/OWNER/REPO --jq '{repo_id: .id, owner_id: .owner.id, full_name: .full_name}'
```

Or, when in doubt, read the claim the runner actually gets by adding a temporary step to the workflow
before `configure-aws-credentials` (safe to print — it is a short-lived identity token payload, and
this prints only the claims, never the token):

```yaml
      - name: Debug OIDC claims
        run: |
          TOKEN=$(curl -sH "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com" | jq -r .value)
          echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{sub, aud, repository, ref}'
```

Pinning `sub` to `...:ref:refs/heads/main` means only a run on `main` can assume the role. The
workflow is `workflow_dispatch`, so dispatch it against `main`.

## Creating the stack without CLI credentials

If the account has no IAM users, there are no access keys and CloudShell will not run as root — the
console is the only way in. With the Chrome tools:

CloudFormation → **Create stack** → *With new resources* → *Choose an existing template* → *Upload a
template file* → `infra/github-oidc.yaml`. Stack name `recall-github-oidc`. On the options step tick
the capabilities checkbox (it asks for **`CAPABILITY_NAMED_IAM`**, because the role has an explicit
`RoleName`). The role ARN comes out under **Outputs → RoleArn**.

To change the trust policy later, use *Update stack → Replace existing template* and re-upload; the
role updates in place.

## Repo secrets and variables

| Kind | Name | Where the value comes from |
|---|---|---|
| secret | `AWS_ROLE_ARN` | `RoleArn` output of the OIDC stack |
| secret | `DATABASE_URL` | `backend/.env` — leave `sslmode=verify-full`, and **no** `sslrootcert=` (see `recall-deploy`) |
| secret | `COCKROACH_MCP_API_KEY` | `backend/.env` |
| secret | `GEMINI_API_KEY` | `backend/.env` |
| variable | `AWS_REGION` | deployment region; must match the `BEDROCK_MODEL_ID` prefix if Bedrock is used |
| variable | `COCKROACH_MCP_URL`, `COCKROACH_MCP_CLUSTER_ID` | `backend/.env` |
| variable | `LLM_PROVIDER`, `EMBEDDING_PROVIDER` | `gemini` today |
| variable | `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`, `BEDROCK_MODEL_ID`, `BEDROCK_EMBEDDING_MODEL_ID` | `backend/.env`; empty is fine, the template has defaults |

Load them from `backend/.env` in one shot without printing anything:

```bash
bash -c 'set -a; source backend/.env; set +a
  gh secret   set DATABASE_URL --body "$DATABASE_URL"
  gh variable set AWS_REGION   --body "$AWS_REGION"'
```

## Also worth checking on a fresh account

- **Lambda concurrency quota** is 10 on new accounts, which makes any `ReservedConcurrentExecutions`
  fail. Service Quotas → Lambda → *Concurrent executions*.
- **Bedrock model access** is off by default, if Bedrock is the chosen provider.
- The workflow must exist on the **default branch** before `workflow_dispatch` will offer it.
