# Minitex training session
This document provides the examples used in the training sessions. The goals in these sessions are to set up a ReShare system and understand the key concepts of the underlying platform. This document shows an example install, but is not necessarily meant to be a guide for best practice installation in a production environment. 

The order of operations here is geared towards wading into reshare administration more than an efficient setup procedure. The end result should be a ReShare system runnin gin a Kubernetes namespace. This includes the ReShare components such as the crosslink broker, reservoir, and directory module. It also includes the user login subsystem from FOLIO, and any infrastructure necessary to support these systems.

## Prerequisites

### Kubernetes namespace
The kubernetes namespace provides logical sepeartion from other areas in the Kubernetes cluster. Create a new [kubernetes namespace](https://kubernetes.io/docs/reference/kubernetes-api/core/namespace-v1/) for the session. We'll call the namespace "reshare" in this example. From the cluster flux repository create a directory and copy the [namespace manifest](./manifests/reshare/reshare-namespace.yaml) into the new namespace directory.


### Chart Repositories
We'll take advantage of a number of Helm charts to deploy software. Configure a help repository for the necessary charts. In this example, repositories are in the "flux-system" namespace. We put them in the "helm-repos" directory in the flux control repository for convenience. Create the helm-repos directory and add the following manifests:
* [bitnami helm repository](./manifests/helm-repos/bitnami-charts.yaml)
* [indexdata public helm repository](./manifests/helm-repos/idgithub-public.yaml)


### Data Storage: Postgresql
The ReShare project uses the postgres database for data persistence. We will provision an number of databases and roles. To begin, we need a datbase for our module data. This database will support N number of ReShare tenants. We also will need a database for [Okapi](https://github.com/folio-org/okapi). Okapi is a proxy and api gateway server which will provide an entrypoint to the software in the ReShare system. 

In this guide, postgres is deployed as a helm chart backed by persistent volumes. The Chart is minimally configred with values to create a module and okapi database. Create a "charts" directory and put the [postgres](./manifests/reshare/charts/postgres.yaml) chart in there. Inspect the chart's values and take note of the database creation script. Credentials are included there for demonstration purposes.

Various components of the ReShare system will need postgres credentials. Store them in a secret at the root of the namespace. Copy the [db-secrets.yaml](./manifests/reshare/db-secrets.yaml) into the root of the "reshare" namespace directory. Inspect the manifest and note the credentials.


### Checkpoint: commit and deploy
At this point the flux cluster control repository should include these items. Commit them and make sure they come up.
```
.
├── helm-repos
│   ├── bitnami-charts.yaml
│   └── idgithub-public.yaml
│   └── okapi.yaml
└── reshare
    ├── charts
    │   └── postgres.yaml
    ├── db-secrets.yaml
    └── reshare-namespace.yaml
```
After flux has picked up the changes, you should be able to see your resources using the kubectl tool. For example:
Show the running pods
```
$ kubectl -n reshare get pods
```
```
NAME                     READY   STATUS    RESTARTS      AGE
resharedb-postgresql-0   1/1     Running   0             38m
```
Check logs that the secret was created, and tail the postgres logs.

### Okapi
[Okapi](https://github.com/folio-org/okap) is the API gateway and proxy server that provides a unified entrypoint to most ReShare components. Okapi can be deployed from a chart. Copy the [okapi.yaml](./manifests/reshare/charts/okapi.yaml) chart into the "charts" repository. Take a look at the configured values. Note the database credentials. Commit the Okapi chart, and verify the statefulset comes up. At this point, create an environment variable with your okapi hostname:

```
export okapi=https://myokapi.mydomain.tld
```

Once Okapi is up we'll need to populate it with module descritpors. We'll do this two ways. First we'll use a special feature to sync all available module descriptors from the FOLIO project to our Okapi. This way we have definitions for all FOLIO modules:

```
echo '{"urls" : [ "https://folio-registry.dev.folio.org" ]}' | http POST $okapi/_/proxy/pull/modules
```

### Secure Okapi
The Okapi supertenant is the default tenant. Enable the authentication subsystem on the supertenant to secure the okapi APIs. The process of securing the supertnant follows these steps:
1. Deploy users, login, permissions, and authentication modules.
1. Enable all modules on the supertenant except for the authentication module.
1. Create a user, permissions, and credential record (at this piont, the APIs are still unsecured).
1. Enable the authentication module to enforce the use of an authentication token.
For

Begin by deploying the required software in the reshare namespace. Copy the "auth-modules" directory into the root of the flux control repository. Inspect the manifests there. For each module, there are two manifests, a deployment and a service. The deployment creates a pod, and the service creates a route to that pod. In the deployment manifest, note that the modules get their database credentials from the shared database secret created by the db-secrets.yaml manifest at the root of the reshare namespace.

### Checkpoint: commit and deploy
A this piont, the flux control repository should include these files:
```
.
├── helm-repos
│   ├── bitnami-charts.yaml
│   └── idgithub-public.yaml
│   └── okapi.yaml
└── reshare
    ├── auth-modules
    │   ├── mod-authtoken-2.16.2
    │   │   ├── deployment.yaml
    │   │   └── service.yaml
    │   ├── mod-login-7.12.1
    │   │   ├── deployment.yaml
    │   │   └── service.yaml
    │   ├── mod-permissions-6.6.1
    │   │   ├── deployment.yaml
    │   │   └── service.yaml
    │   └── mod-users-19.6.0
    │       ├── deployment.yaml
    │       └── service.yaml
    ├── charts
    │   ├── okapi.yaml
    │   └── postgres.yaml
    ├── db-secrets.yaml
    └── reshare-namespace.yaml
```
Commit these and let flux pick up the changes. Check that the pods are running, and look at the services that were created:
```
kubectl -n reshare get svc
```
These are the internal addresses for the modules that were just deployed. The will be used in the next steps.

### Secure Okapi, continued
All software for securing Okapi is running on kubernetes. Module descriptors were pulled from the FOLIO registry. To make Okapi aware of the instances of these modules running on kubernetes, post a deployment descriptor for each module. Use the post-deployment-descriptors.py script to create the descriptors:
```
python3 scripts/post-deployent-descriptors.py -o $okapi -d resources/1-supertenant/deployment-descriptors/
```

Finally, use the secure-supertenant.py script to bootstrap a superuser:
```
python3 scripts/secure-supertenant.py -u okapi_admin  -o $okapi
```
Try logging in to the supertenant, and save a token
```
http POST $okapi/authn/logon username=okapi_admin password=okapiadmin123
```
```
export token=my.okapi.token
```

## Reservoir
Reservoir is deployed on a new tenant. In a typical ReShare configuration, there is one instance of reservoir that serves a consortium. Reservoir is on its own tenant, and each institution has a tenant for the ReShare software. This section walks through creating the Reservoir tenant manually.

### Create a new tenant for Reservoir
```
cat resources/2-reservoir/tenant.json | http POST $okapi/_/proxy/tenants "x-okapi-token:$token"
```
The `/_/proxy/tenants` api should now list two tenants, the supertnant, and the new reservoir tenant.

### Deploy the reservoir software
Reservoir is deployed from a chart. Copy the "reservoir.yaml" file into the charts directory of the reshare namespace and commit the change. Next, post the module descriptor and deployment descriptors:
```
cat resources/2-reservoir/reservoir-md.json | http POST $okapi/_/proxy/modules "x-okapi-token:$token"
```
```
cat resources/2-reservoir/reservoir-dd.json | http POST $okapi/_/discovery/modules "x-okapi-token:$token"
```
All the software required for the reservoir tenant is now deployed. Its [listed](resources/2-reservoir/install.json) in the `resources/2-reservoir/install.json` file. We can enable all module simultaneously by using Okapi's [install](https://github.com/folio-org/okapi/blob/master/doc/guide.md#install-modules-per-tenant) api. Its useful to simulate an install first to confirm that all required software is present.
```
cat resources/2-reservoir/install.json | http POST $okapi/_/proxy/tenants/reservoir/install?simulate=true
```
If the the response reflects the set of modules in the install file, remove the "simulate" query parameter and enable the required modules for the reservoir tenant.
```
cat resources/2-reservoir/install.json | http POST $okapi/_/proxy/tenants/reservoir/install
```

### Create a superuser for the reservoir tenant
There are no users on the reservoir tenant. Additionally, mod-authtoken is enabled so it is completely locked off. We can bootstrap a superuser using a script to disable mod-authtoken then create a user, permissions user, and login credential before re-enabling mod-authtoken. Run the bootstrap-tenant-admin.py script.
```
python3 scripts/create-tenant-admin.py -o $mokapi -u okapi_admin -a reservoir_admin -t reservoir
```