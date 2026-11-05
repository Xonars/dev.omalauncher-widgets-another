# TAGLINE

Command-line client for Tigris S3-compatible object storage

# TLDR

**Authenticate** the CLI against your Tigris account

```tigris login```

**Show** the currently logged-in user and active account

```tigris whoami```

**Create** a new bucket

```tigris bucket mk [bucket_name]```

**List** all buckets in your account

```tigris ls```

**List** objects inside a bucket

```tigris ls t3://[bucket_name]/```

**Copy** a local file into a bucket

```tigris cp [path/to/file] t3://[bucket_name]/[key]```

**Recursively copy** a directory to a bucket

```tigris cp -r [path/to/dir] t3://[bucket_name]/[prefix]/```

**Download** an object to a local path

```tigris cp t3://[bucket_name]/[key] [path/to/file]```

**Delete** an object or recursively a prefix

```tigris rm -r t3://[bucket_name]/[prefix]/```

# SYNOPSIS

**tigris** _domain_ _operation_ [_argument_] [**--flags**]
**t3** _domain_ _operation_ [_argument_] [**--flags**]

# PARAMETERS

**login**
> Open a browser-based flow to authenticate the CLI against Tigris (or Fly.io for Fly-managed buckets).

**logout**
> Remove cached credentials.

**whoami**
> Print the active user and account.

**configure**
> Interactively configure profiles, endpoints, and access keys for non-interactive use.

**bucket mk** _name_ [**--region** _region_] [**--public**]
> Create a new bucket. Bucket names share Tigris' global namespace.

**bucket ls**
> List buckets owned by the active account.

**bucket rm** _name_
> Delete an empty bucket.

**ls** [_t3-uri_]
> List buckets when given no argument, or list keys under a bucket / prefix when given a **t3://** URI.

**cp** [**-r**] [**--acl** _acl_] [**--content-type** _type_] _src_ _dst_
> Copy data between local paths and **t3://** URIs. Either side may be local or remote, enabling local-to-remote, remote-to-local, or remote-to-remote copies.

**rm** [**-r**] _t3-uri_
> Delete a single object, or recursively delete a prefix with **-r**.

**touch** _t3-uri_
> Create a zero-byte object at the given key.

**presign** _t3-uri_ [**--expires** _duration_] [**--method** _GET\|PUT_]
> Generate a pre-signed URL for sharing a single object without credentials.

**--profile** _name_
> Use a named profile from the configuration file.

**--endpoint** _url_
> Override the Tigris endpoint (defaults to **fly.storage.tigris.dev**).

**--output** _format_
> _table_, _json_, or _yaml_ output.

**-v**, **--verbose**
> Verbose logging.

**--help**
> Show help for any command.

# DESCRIPTION

**tigris** is the official command-line client for **Tigris**, a globally distributed, S3-compatible object storage service. The CLI presents an intentionally **UNIX-flavoured** interface modelled after **ls**, **cp**, **rm**, and **touch**, with **t3://_bucket_/_key_** URIs identifying remote objects.

The CLI groups commands by domain - **bucket**, **object**, **iam**, **config** - and each domain exposes a small, predictable set of operations. Because Tigris is S3-compatible, anything **tigris** can do is also reachable via the **AWS CLI** by pointing **--endpoint-url** at the Tigris endpoint; the dedicated CLI mainly improves ergonomics, login flow, and bucket lifecycle management.

When a bucket is provisioned through **Fly.io** (using **fly storage create**), the same credentials and endpoints work seamlessly with **tigris**, and a short alias **t3** is available for terser one-liners.

# CONFIGURATION

Credentials and profiles live under _~/.config/tigris/config.toml_:

```
[default]
access_key_id = "tid_..."
secret_access_key = "tsec_..."
endpoint = "https://fly.storage.tigris.dev"
region = "auto"
```

Environment variables override the file:

```
TIGRIS_ACCESS_KEY_ID
TIGRIS_SECRET_ACCESS_KEY
TIGRIS_ENDPOINT_URL
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_ENDPOINT_URL_S3
```

Standard **AWS_*** variables are honoured so existing S3 tooling can target Tigris without code changes. **tigris configure** writes the same file interactively.

# CAVEATS

The **tigris** CLI is distinct from any historical **TigrisData** database CLI of the same name; the modern client targets the **Tigris Object Storage** product run on Fly.io infrastructure. Bucket names are **globally unique**, similar to S3. Pre-signed URLs respect bucket ACLs, so a private bucket plus a presigned URL is the correct way to share an object publicly for a limited time.

# HISTORY

**Tigris** launched as the storage layer for **Fly.io** applications and is operated by **Tigris Data**. The dedicated CLI was introduced to provide a focused alternative to the AWS CLI for everyday bucket operations, with the **t3** shorthand and **t3://** URI scheme borrowing the ergonomics of **s3cmd** and **rclone**.

# SEE ALSO

[aws](/man/aws)(1), [s3cmd](/man/s3cmd)(1), [rclone](/man/rclone)(1), [flyctl](/man/flyctl)(1), [mc](/man/mc)(1)
