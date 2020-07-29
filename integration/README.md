# Teal Integration Tests

All user-level testing.


## AWS Account Setup

These tests have to be run with a real AWS account, because the localstack
community version doesn't support Lambda Layers.

The recommended approach is to create a new IAM user for running these tests,
and assign the IAM permissions listed in `./test_user_policy.json`. The process
to do that is described here.

**Don't use an account with production data in it!**


### Step 1: Create an IAM user

Go to
[https://console.aws.amazon.com/iam/home](https://console.aws.amazon.com/iam/home),
select "Users" under **Access Management**, and hit "Add user".

Under **Access Type**, select "Programmatic access" *only*.

In **Set Permissions**, select "Attach existing policies directly", and hit
"Create policy".

In the New Policy tab, select JSON, and copy in the contents of
[test_user_policy.json](./test_user_policy.json).

Back in the Add User tab, select the policy you've just created.

Finish the new user creation process and save the `ACCESS_KEY_ID` and
`SECRET_ACCESS_KEY` for step 2.


### Step 2: Create `stories/.env`

The test harness uses AWS credentials stored in `stories/.env`.

`stories/.env` needs the following variables. Fill in the access key blanks with
the details from your user in step 1.

```
AWS_DEFAULT_REGION=eu-west-2
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```


## Test Stories

Tests are grouped into user stories (start-to-finish journey of a Teal user
accomplishing something).

Each test story has a `test.sh` file which defines the user actions, and a
`Dockerfile` which defines the environment image.

For each story, run one of:
- `make test` to test the latest PyPI version of Teal
- `TEAL_VERSION="==x.x.x" make test` for a specific PyPI version (note the "==" prefix)
- `make local` to test this Teal checkout
- `make local-nobuild` to test this Teal checkout without rebuilding Teal (e.g.
  if `test.sh` has changed)


If you don't have `make` installed, or don't like it, grab the commands in
[stories/common.mk](stories/common.mk) and call them directly.


### Getting Started

Runs the 2 minute getting-started tutorial.


### Try Fractals

Runs the fractals example. `stories/.env` needs `FRACTALS_BUCKET` to be defined.


## Troubleshooting

In the worst case, a test will fail, and you'll be left with a Teal instance in
your account.

To solve that, run `teal destroy --uuid $UUID` where `$UUID` is the UUID of the
instance created in the test (this should be shown the test logs).