"""Generate FalkorDB Cloud API reference MDX pages from the Omnistrate OpenAPI spec.

Usage: python3 scripts/generate_api_pages.py /path/to/openapi.json
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = "https://api.omnistrate.cloud"
PREFIX = "/2022-09-01-00/resource-instance/sp-JvkxkPhinN/falkordb/v1/prod/"

TIERS = {
    "falkordb-enterprise-byoa-byoa": ("enterprise-byoa", "Enterprise BYOA"),
    "falkordb-enterprise-customer-hosted": (
        "enterprise",
        "Enterprise",
    ),
    "falkordb-pro-customer-hosted": ("pro", "Pro"),
    "falkordb-startup-customer-hosted": ("startup", "Startup"),
    "falkordb-free-customer-hosted": ("free", "Free"),
}

COMPONENTS = {
    "standalone": ("standalone", "Standalone"),
    "cluster-Multi-Zone": ("cluster-multi-zone", "Cluster (Multi-Zone)"),
    "cluster-Single-Zone": ("cluster-single-zone", "Cluster (Single-Zone)"),
    "multi-Zone": ("multi-zone", "Multi-Zone"),
    "single-Zone": ("single-zone", "Single-Zone"),
    "free": ("free", "Free"),
}

OPERATION_ORDER = [
    "list",
    "create",
    "describe",
    "update",
    "delete",
    "backup",
    "copy-snapshot",
    "failover",
    "start",
    "stop",
    "restart",
]

TITLES = {
    "list": ("List instances", "List"),
    "create": ("Create instance", "Create"),
    "describe": ("Describe instance", "Describe"),
    "update": ("Update instance", "Update"),
    "delete": ("Delete instance", "Delete"),
    "backup": ("Trigger backup", "Backup"),
    "copy-snapshot": ("Copy snapshot", "Copy snapshot"),
    "failover": ("Failover replica", "Failover"),
    "start": ("Start instance", "Start"),
    "stop": ("Stop instance", "Stop"),
    "restart": ("Restart instance", "Restart"),
}

SUMMARIES = {
    "list": "List the IDs of all {r} instances in your subscription.",
    "create": "Provision a new {r} instance.",
    "describe": "Get the current configuration and status of {a} {r} instance.",
    "update": "Update the configuration of {a} {r} instance.",
    "delete": "Permanently delete {a} {r} instance and its data.",
    "backup": "Trigger an on-demand backup of {a} {r} instance.",
    "copy-snapshot": "Copy a snapshot of {a} {r} instance to another region.",
    "failover": "Fail over a replica of {a} {r} instance.",
    "start": "Start a stopped {r} instance.",
    "stop": "Stop a running {r} instance without deleting it.",
    "restart": "Restart {a} {r} instance.",
}

INTROS = {
    "list": "Returns the IDs of every {r} instance you can access. Use [Describe]({base}/describe) to fetch the details of an individual instance.",
    "create": "Provisions a new {r} instance in the requested cloud provider and region. The instance is created asynchronously; poll [Describe]({base}/describe) until `status` is `RUNNING`.",
    "describe": "Returns the deployment metadata, connection details, and current lifecycle status of a single instance.",
    "update": "Applies configuration changes to a running instance. Only the fields you send are changed. Changing `falkordbPassword` or `nodeInstanceType` restarts the instance.",
    "delete": "Deletes the instance and all of its data. This action cannot be undone.",
    "backup": "Starts an on-demand backup. Backups run asynchronously and do not interrupt the instance.",
    "copy-snapshot": "Copies an existing snapshot into another region, for example to seed a disaster-recovery deployment.",
    "failover": "Promotes a healthy replica and replaces the failed one. Use this when a replica becomes unavailable.",
    "start": "Starts an instance that was previously stopped. Billing for compute resumes once the instance is running.",
    "stop": "Stops the instance's compute while retaining its storage and configuration. Use [Start]({base}/start) to bring it back online.",
    "restart": "Performs a rolling restart of the instance's nodes.",
}


def op_name(path: str, method: str) -> str:
    tail = path.split("/")[-1]
    if tail.startswith("{"):
        return {"get": "describe", "put": "update", "delete": "delete"}[method]
    if tail in ("backup", "copy-snapshot", "failover", "start", "stop", "restart"):
        return tail
    return {"get": "list", "post": "create"}[method]


def fmt_default(value):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return " default={%s}" % ("true" if value else "false")
    if isinstance(value, (int, float)):
        return " default={%s}" % value
    return ' default="%s"' % value


def clean(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


FDB_CONFIG_DOCS = "https://docs.falkordb.com/getting-started/configuration.html"


def config_link(anchor, label):
    return "Maps to [`%s`](%s#%s) in the FalkorDB configuration." % (
        label,
        FDB_CONFIG_DOCS,
        anchor,
    )


FIELD_DOCS = {
    "cloud_provider": "Cloud provider to provision the instance on, for example `aws` or `gcp`.",
    "region": "Region to provision the instance in, for example `us-east-1`.",
    "custom_network_id": "ID of the custom network to provision the instance in.",
    "cloud_provider_account_config_id": "ID of the cloud provider account configuration that FalkorDB deploys into.",
    "cloud_provider_native_network_id": "ID of an existing network in your cloud account to attach the instance to.",
    "name": "Human-readable name for the instance.",
    "description": "Description of the instance.",
    "nodeInstanceType": "Compute instance type used for each node. See [Instance configuration](/api-reference/schemas#instance-configuration).",
    "maxMemory": "Maximum memory available to the database, for example `6GB`. Do not exceed the memory of the selected instance type.",
    "memoryRequestsAndLimits": "Memory requested for and allocated to the database, for example `1GB`. Set at creation only.",
    "numReplicas": "Number of replicas to deploy. Fixed at `2`.",
    "falkordbUser": "Default username for the database. Set at creation only.",
    "falkordbPassword": "Default password for the database. Updating this value after deployment restarts the instance.",
    "enableTLS": "Enable TLS for database connections. Set at creation only.",
    "enableEnterpriseModule": "Enable the FalkorDB enterprise module. Set at creation only.",
    "AOFPersistenceConfig": "Append-only file persistence mode. One of `everysec` or `always`. Set at creation only.",
    "RDBPersistenceConfig": "How often the RDB snapshot is written to disk. One of `low`, `medium`, or `high`. Set at creation only.",
    "falkorDBCacheSize": "Number of cached query executions. Between `1` and `256`. Set at creation only. "
    + config_link("cache_size", "CACHE_SIZE"),
    "falkorDBMaxQueuedQueries": "Maximum number of queries that can be queued. Between `1` and `512`. Set at creation only. "
    + config_link("max_queued_queries", "MAX_QUEUED_QUERIES"),
    "falkorDBNodeCreationBuffer": "Node creation buffer size. Between `256` and `32768`. Set at creation only. "
    + config_link("node_creation_buffer", "NODE_CREATION_BUFFER"),
    "falkorDBQueryMemCapacity": "Maximum memory a single query may use, in bytes. Between `5242880` (5 MiB) and `21474836480` (20 GiB). Set at creation only. "
    + config_link("query_mem_capacity", "QUERY_MEM_CAPACITY"),
    "falkorDBResultSetSize": "Maximum number of records returned by a query. Between `0` and `1000000`, where `0` means unlimited. Set at creation only. "
    + config_link("resultset_size", "RESULTSET_SIZE"),
    "falkorDBTimeoutDefault": "Default query timeout in milliseconds. Between `0` and `45000`, where `0` disables the timeout. Set at creation only. "
    + config_link("timeout_default", "TIMEOUT_DEFAULT"),
    "falkorDBTimeoutMax": "Maximum query timeout in milliseconds. Between `0` and `45000`, where `0` disables the limit. Set at creation only. "
    + config_link("timeout_max", "TIMEOUT_MAX"),
    "source_snapshot_id": "ID of the snapshot to copy from.",
    "target_region": "Region to copy the snapshot to.",
    "failed_replica_id": "ID of the failed replica to fail over from.",
    "failed_replica_action": "Action to take on the failed replica.",
}

RESPONSE_DOCS = {
    "id": "ID of the resource instance.",
    "ids": "IDs of the resource instances.",
    "status": "Lifecycle status of the instance, for example `RUNNING` or `STOPPED`.",
    "cloud_provider": "Cloud provider the instance runs on.",
    "region": "Region the instance runs in.",
    "network_type": "Network type of the instance.",
    "created_at": "Time the instance was created.",
    "last_modified": "Time the instance was last modified.",
    "result_params": "Deployment outputs, including connection endpoints and credentials.",
    "custom_network": "Custom network the instance is provisioned in.",
    "snapshot_id": "ID of the snapshot that was created.",
}


def describe_field(name, spec):
    return FIELD_DOCS.get(name) or clean(spec.get("description")) or name


def param_field(name, spec, required, kind="body"):
    ftype = spec.get("type", "string")
    if ftype == "array":
        ftype = spec.get("items", {}).get("type", "string") + "[]"
    req = " required" if required else ""
    return '<ParamField %s="%s" type="%s"%s%s>\n  %s\n</ParamField>' % (
        kind,
        name,
        ftype,
        fmt_default(spec.get("default")),
        req,
        describe_field(name, spec),
    )


def render_body(schema):
    out = []
    required = set(schema.get("required", []))
    props = schema.get("properties", {})
    for name, spec in sorted(props.items(), key=lambda kv: (kv[0] == "requestParams", kv[0])):
        if name == "requestParams":
            inner_required = set(spec.get("required", []))
            inner = spec.get("properties", {})
            lines = [
                '<ParamField body="requestParams" type="object" required>',
                "  Instance configuration.",
                "",
                '  <Expandable title="requestParams properties">',
            ]
            for key in sorted(
                inner, key=lambda k: (k not in inner_required, k.lower())
            ):
                block = param_field(key, inner[key], key in inner_required)
                lines.append("\n".join("    " + ln if ln else "" for ln in block.split("\n")))
                lines.append("")
            lines.pop()
            lines.append("  </Expandable>")
            lines.append("</ParamField>")
            out.append("\n".join(lines))
        else:
            out.append(param_field(name, spec, name in required))
    return "\n\n".join(out)


def render_response_fields(schema):
    out = []
    required = set(schema.get("required", []))
    for name, spec in schema.get("properties", {}).items():
        ftype = spec.get("type", "object")
        if ftype == "array":
            ftype = spec.get("items", {}).get("type", "string") + "[]"
        out.append(
            '<ResponseField name="%s" type="%s"%s>\n  %s\n</ResponseField>'
            % (
                name,
                ftype,
                " required" if name in required else "",
                RESPONSE_DOCS.get(name) or clean(spec.get("description")),
            )
        )
    return "\n\n".join(out)


EXAMPLES = {
    "list": '```json 200 OK\n{\n  "ids": ["instance-abc123", "instance-def456"]\n}\n```',
    "create": '```json 202 Accepted\n{\n  "id": "instance-abc123"\n}\n```',
    "copy-snapshot": '```json 200 OK\n{\n  "snapshot_id": "snapshot-abc123"\n}\n```',
}


def describe_example(has_custom_network):
    body = {
        "id": "instance-abc123",
        "status": "RUNNING",
        "cloud_provider": "aws",
        "region": "us-east-1",
        "network_type": "PUBLIC",
        "created_at": "2026-01-15T10:30:00Z",
        "last_modified": "2026-01-20T08:12:00Z",
        "result_params": {
            "falkordbHostname": "abc123.instances.omnistrate.cloud",
            "falkordbPort": 6379,
        },
    }
    if has_custom_network:
        body["custom_network"] = "network-abc123"
    return "```json 200 OK\n%s\n```" % json.dumps(body, indent=2)


PRO_INSTANCE_TYPES = [
    ("AWS", "t4g.medium", 2, 4),
    ("AWS", "m7g.large", 2, 8),
    ("AWS", "r7g.large", 2, 16),
    ("AWS", "c7g.xlarge", 4, 8),
    ("AWS", "m7g.xlarge", 4, 16),
    ("AWS", "r7g.xlarge", 4, 32),
    ("AWS", "c7g.2xlarge", 8, 16),
    ("AWS", "m7g.2xlarge", 8, 32),
    ("AWS", "r7g.2xlarge", 8, 64),
    ("AWS", "c7g.4xlarge", 16, 32),
    ("AWS", "m7g.4xlarge", 16, 64),
    ("AWS", "r7g.4xlarge", 16, 128),
    ("AWS", "c7g.8xlarge", 32, 64),
    ("AWS", "m7g.8xlarge", 32, 128),
    ("GCP", "e2-medium", 2, 4),
    ("GCP", "e2-standard-2", 2, 8),
    ("GCP", "e2-highmem-2", 2, 16),
    ("GCP", "e2-custom-4-8192", 4, 8),
    ("GCP", "e2-standard-4", 4, 16),
    ("GCP", "e2-highmem-4", 4, 32),
    ("GCP", "e2-custom-8-16384", 8, 16),
    ("GCP", "e2-standard-8", 8, 32),
    ("GCP", "e2-highmem-8", 8, 64),
    ("GCP", "e2-custom-16-32768", 16, 32),
    ("GCP", "e2-custom-32-65536", 32, 64),
]


def pro_instance_type_table():
    rows = [
        "| Cloud provider | `nodeInstanceType` | vCPU | Memory |",
        "| --- | --- | --- | --- |",
    ]
    for provider, value, cpu, mem in PRO_INSTANCE_TYPES:
        rows.append("| %s | `%s` | %d | %d GB |" % (provider, value, cpu, mem))
    return "\n".join(rows)


# Sizing and per-tier availability, taken from the service definition.
TIER_CONFIG = {
    "enterprise-byoa": {
        "sizing": (
            "`nodeInstanceType` accepts any compute instance type available to your "
            "Enterprise BYOA plan in the selected cloud provider and region, for example "
            "`e2-custom-4-8192` on GCP or `m7g.xlarge` on AWS. It defaults to "
            "`e2-custom-4-8192`. Use `maxMemory` to cap the memory the database itself "
            "uses; it must not exceed the memory of the selected instance type."
        ),
        "available": "`maxMemory` and `enableEnterpriseModule` are available on this tier.",
    },
    "enterprise": {
        "sizing": (
            "`nodeInstanceType` accepts any compute instance type available to your "
            "Enterprise plan in the selected cloud provider and region, for example "
            "`e2-custom-4-8192` on GCP or `m7g.xlarge` on AWS. It defaults to "
            "`e2-custom-4-8192`. Use `maxMemory` to cap the memory the database itself "
            "uses; it must not exceed the memory of the selected instance type."
        ),
        "available": "`maxMemory` and `enableEnterpriseModule` are available on this tier.",
    },
    "pro": {
        "sizing": (
            "`nodeInstanceType` is required and must be one of the instance types below. "
            "The list differs from the Enterprise tiers, which accept any instance type "
            "available to the plan.\n\n" + pro_instance_type_table()
        ),
        "available": (
            "`maxMemory` and `enableEnterpriseModule` are **not** available on the Pro "
            "tier. Memory is determined by the selected `nodeInstanceType`."
        ),
    },
    "startup": {
        "sizing": (
            "The Startup tier does not expose `nodeInstanceType`. Size the database with "
            "`memoryRequestsAndLimits` instead, which accepts `1200M` (1 GB, the default) "
            "or `2200M` (2 GB)."
        ),
        "available": (
            "`nodeInstanceType`, `numReplicas`, `maxMemory`, and `enableEnterpriseModule` "
            "are **not** available on the Startup tier."
        ),
    },
    "free": {
        "sizing": (
            "The Free tier is fixed size and does not expose any sizing parameters."
        ),
        "available": (
            "Only `name`, `description`, `falkordbUser`, and `falkordbPassword` are "
            "available on the Free tier. Sizing, TLS, persistence, and the `falkorDB*` "
            "tuning parameters are **not** configurable."
        ),
    },
}

REPLICA_NOTE = (
    "`numReplicas` is fixed at `2` for this component and cannot be changed."
)


def tier_config_section(tier_dir, comp_dir):
    cfg = TIER_CONFIG[tier_dir]
    parts = ["## Sizing and tier availability", "", cfg["sizing"], "", cfg["available"]]
    if comp_dir in ("single-zone", "multi-zone"):
        parts += ["", REPLICA_NOTE]
    parts += [
        "",
        "See [Instance configuration](/api-reference/schemas#instance-configuration) "
        "for the full field reference.",
        "",
    ]
    return "\n".join(parts)


def build_page(spec, path, method, tier_dir, comp_dir, resource):
    op = op_name(path, method)
    base = "/api-reference/%s/%s" % (tier_dir, comp_dir)
    schemas = spec["components"]["schemas"]
    operation = spec["paths"][path][method]
    title, sidebar = TITLES[op]
    article = "an" if resource[0] in "AEIOU" else "a"
    lines = [
        "---",
        'title: "%s"' % title,
        'sidebarTitle: "%s"' % sidebar,
        'api: "%s %s%s"' % (method.upper(), BASE_URL, path),
        'description: "%s"' % SUMMARIES[op].format(r=resource, a=article),
        "---",
        "",
        INTROS[op].format(r=resource, a=article, base=base),
        "",
        "## Authorization",
        "",
        '<ParamField header="Cookie" type="string" required>',
        "  Session cookie set by [Sign in](/api-reference/authentication/signin): `omnistrate_token=<jwt>`.",
        "  Browsers send it automatically; other clients must forward it on every request.",
        "</ParamField>",
        "",
    ]

    if "{id}" in path:
        lines += [
            "## Path parameters",
            "",
            '<ParamField path="id" type="string" required>',
            "  ID of the resource instance.",
            "</ParamField>",
            "",
        ]

    lines += [
        "## Query parameters",
        "",
        '<ParamField query="subscriptionId" type="string">',
        "  ID of the subscription that owns the instance.",
        "</ParamField>",
        "",
    ]

    request_body = operation.get("requestBody")
    if request_body:
        ref = list(request_body["content"].values())[0]["schema"]["$ref"].split("/")[-1]
        lines += ["## Body", "", render_body(schemas[ref]), ""]

    if op in ("create", "update"):
        lines += [tier_config_section(tier_dir, comp_dir)]

    lines += ["## Response", ""]
    response_ref = None
    for code, resp in operation.get("responses", {}).items():
        for content in resp.get("content", {}).values():
            ref = content.get("schema", {}).get("$ref")
            if ref:
                response_ref = ref.split("/")[-1]
    if response_ref:
        lines += [render_response_fields(schemas[response_ref]), ""]
        if op == "describe":
            lines += [describe_example(response_ref == "DESCRIBEResponseBody2"), ""]
        elif op in EXAMPLES:
            lines += [EXAMPLES[op], ""]
    else:
        lines += [
            "Returns `202 Accepted` with an empty body when the operation is queued.",
            "",
        ]

    lines += [
        "## Errors",
        "",
        "See [Error](/api-reference/schemas#error) for the shared error response shape.",
        "",
    ]
    return "\n".join(lines)


# Hand-written account management pages, kept in the nav across regenerations.
ACCOUNT_GROUP = {
    "group": "Account management",
    "pages": [
        "api-reference/account/service-plans",
        {
            "group": "Subscriptions",
            "pages": [
                "api-reference/account/subscriptions/list",
                "api-reference/account/subscriptions/create",
                "api-reference/account/subscriptions/describe",
                "api-reference/account/subscriptions/delete",
            ],
        },
        {
            "group": "Access control",
            "pages": [
                "api-reference/account/access/list-users",
                "api-reference/account/access/invite-user",
                "api-reference/account/access/revoke-user",
            ],
        },
        "api-reference/account/user/describe",
    ],
}

CLOUD_ACCOUNT_GROUP = {
    "group": "Cloud accounts",
    "pages": [
        "api-reference/cloud-accounts/overview",
        "api-reference/cloud-accounts/create",
        "api-reference/cloud-accounts/describe",
        "api-reference/cloud-accounts/connection",
    ],
}

CUSTOM_NETWORK_GROUP = {
    "group": "Custom networks",
    "pages": [
        "api-reference/networking/list",
        "api-reference/networking/create",
        "api-reference/networking/describe",
        "api-reference/networking/update",
        "api-reference/networking/delete",
    ],
}

SNAPSHOT_GROUP = {
    "group": "Snapshots",
    "pages": [
        "api-reference/snapshots/list",
        "api-reference/snapshots/create",
        "api-reference/snapshots/describe",
        "api-reference/snapshots/restore",
        "api-reference/snapshots/copy",
        "api-reference/snapshots/delete",
    ],
}

# Served from the FalkorDB API host, not Omnistrate.
DATABASE_USER_GROUP = {
    "group": "Database users",
    "pages": [
        "api-reference/database-users/overview",
        "api-reference/database-users/list",
        "api-reference/database-users/create",
        "api-reference/database-users/update",
        "api-reference/database-users/delete",
    ],
}


def main():
    spec_path = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    spec = json.load(open(spec_path))
    nav = {}

    for path, methods in spec["paths"].items():
        if not path.startswith(PREFIX):
            continue
        rest = path[len(PREFIX):]
        parts = rest.split("/")
        tier_key, _model, component = parts[0], parts[1], parts[2]
        if tier_key not in TIERS or component not in COMPONENTS:
            continue
        tier_dir, tier_label = TIERS[tier_key]
        comp_dir, comp_label = COMPONENTS[component]
        resource = (
            "Free"
            if tier_dir == "free"
            else "%s %s" % (tier_label, comp_label)
        )
        for method, operation in methods.items():
            op = op_name(path, method)
            out_dir = os.path.join(ROOT, "api-reference", tier_dir, comp_dir)
            os.makedirs(out_dir, exist_ok=True)
            content = build_page(spec, path, method, tier_dir, comp_dir, resource)
            with open(os.path.join(out_dir, op + ".mdx"), "w") as fh:
                fh.write(content)
            nav.setdefault((tier_dir, tier_label), {}).setdefault(
                (comp_dir, comp_label), set()
            ).add(op)

    groups = []
    for (tier_dir, tier_label) in sorted(
        nav, key=lambda t: list(v[0] for v in TIERS.values()).index(t[0])
    ):
        comp_groups = []
        for (comp_dir, comp_label) in sorted(
            nav[(tier_dir, tier_label)],
            key=lambda c: list(v[0] for v in COMPONENTS.values()).index(c[0]),
        ):
            ops = nav[(tier_dir, tier_label)][(comp_dir, comp_label)]
            pages = [
                "api-reference/%s/%s/%s" % (tier_dir, comp_dir, op)
                for op in OPERATION_ORDER
                if op in ops
            ]
            comp_groups.append({"group": comp_label, "pages": pages})
        groups.append({"group": tier_label, "pages": comp_groups})

    with open(os.path.join(ROOT, "docs.json")) as fh:
        docs = json.load(fh)
    for tab in docs["navigation"]["tabs"]:
        if tab["tab"] == "API Reference":
            tab["pages"] = [
                "api-reference/introduction",
                "api-reference/schemas",
                {
                    "group": "Authentication",
                    "pages": [
                        "api-reference/authentication/signin",
                        "api-reference/authentication/logout",
                    ],
                },
                ACCOUNT_GROUP,
                CLOUD_ACCOUNT_GROUP,
                CUSTOM_NETWORK_GROUP,
                SNAPSHOT_GROUP,
                DATABASE_USER_GROUP,
            ] + groups
    with open(os.path.join(ROOT, "docs.json"), "w") as fh:
        json.dump(docs, fh, indent=2)
        fh.write("\n")

    print("generated pages for %d tiers" % len(nav))


if __name__ == "__main__":
    main()
