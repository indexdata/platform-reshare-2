# Minitex training session
This document provides the examples used in the training sessions. The goals in these sessions are to set up a ReShare system and understand the key concepts of the underlying platform. This document shows an example install, but is not necessarily meant to be a guide for best practice installation in a production environment. 

The order of operations here is geared towards wading into reshare administration more than an efficient setup procedure. The end result should be a ReShare system runnin gin a Kubernetes namespace. This includes the ReShare components such as the crosslink broker, reservoir, and directory module. It also includes the user login subsystem from FOLIO, and any infrastructure necessary to support these systems.

## Prerequisites

### Kubernetes namespace
The kubernetes namespace provides logical sepeartion from other areas in the Kubernetes cluster. Create a new [kubernetes namespace](https://kubernetes.io/docs/reference/kubernetes-api/core/namespace-v1/) for the session. We'll call the namespace "reshare" in this example. From the cluster flux repository create a directory and copy the [namespace manifest](./manifests/reshare/reshare-namespace.yaml) into the new namespace directory.


### Chart Repositories
We'll take advantage of a number of Helm charts to deploy software. Configure a helm repository for the included charts. In this example, repositories are in the "flux-system" namespace. We put them in the "helm-repos" directory in the flux control repository for convenience. Create the helm-repos directory and add the following manifests:
* [bitnami helm repository](./manifests/helm-repos/bitnami-charts.yaml)
* [indexdata public helm repository](./manifests/helm-repos/idgithub-public.yaml)
* [Okapi helm repository](./manifests/helm-repos/okapi.yaml)


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
Check that the secret was created, and tail the postgres logs.

### Okapi
[Okapi](https://github.com/folio-org/okapi) is the API gateway and proxy server that provides a unified entrypoint to most ReShare components. Okapi can be deployed from a chart. Copy the [okapi.yaml](./manifests/reshare/charts/okapi.yaml) chart into the "charts" repository. Take a look at the configured values. Note the database credentials. *Commit the Okapi chart*, and verify the statefulset comes up. At this point, create an environment variable with your okapi hostname:

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

### Checkpoint: Okapi and login software
A this point, the flux control repository should include these files:
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

 -------------------------- WIP ----------------------------
## ReShare Tenants
The ReShare tenants used by ILL staff to manage loans are comprised of the ReShare softwware plus a base set of FOLIO modules to provide authn/z, user namangement, and mail. 

Begin by cloning the [reshare-ui](https://github.com/indexdata/reshare-ui) into the "repos" directory:
```
git clone https://github.com/indexdata/reshare-ui.git repos/reshare-ui
```
We will be using this repository to build the front end webpack, and enable the remaining base modules on the ReShare tenant.

Begin by creating a new tenant for reshare. In this example, the tenant id is "rs1"

```
cat resources/3-reshare/tenant.json | http POST $okapi/_/proxy/tenants
```

### FOLIO module deployment
The remaining FOLIO modules are in the `./manifests/reshare/modules` directory. Copy them into your flux control repository. 

Add the deployment descriptors form the `./resources/3-reshare/deployment-descriptors` directory:

```
python3 scripts/post-deployent-descriptors.py -o $okapi -u okapi_admin -p okapiadmin123 -d resources/3-reshare/deployment-descriptors/
```

#### ReShare Chart Manifests
We will enable the directory, and broker modules on the ReShare tenants. This software is deployed using charts. These charts have the capability to include the okapi hooks chart as a dependency. Okapi hooks automates the Okapi communication for these modules. To use okapi hooks, we need to first create a secret with the okapi credentials. Copy the "okapi-secrets.yaml" secret from `./manifests/reshare/okapi-secrets.yaml` into the root of your flux control repository.

We will deploy the optional crosslink-illmock chart to mock all integration we may want to test. It requires a directory configureation. Copy the `./manifests/reshare/directory-configmap.yaml` manifest into the root of your flux control repository.

Finally, copy the broker.yaml, directory.yaml, and mock.yaml charts from `./manifests/reshare/charts` into the charts directory of your flux control repository.

### Checkpoint: Deploy
At this point, your flux control repository should include the following manifests:
```
.
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
│   ├── broker.yaml
│   ├── directory.yaml
│   ├── mock.yaml
│   ├── okapi.yaml
│   ├── postgres.yaml
│   └── reservoir.yaml
├── db-secrets.yaml
├── directory-configmap.yaml
├── reshare-namespace.yaml
├── modules
│   ├── mod-configuration-5.11.0
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── mod-notes-6.0.0
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── mod-password-validator-3.3.0
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── mod-settings-1.1.0
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── mod-tags-2.3.0
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── mod-users-bl-7.9.4
│       ├── deployment.yaml
│       └── service.yaml
└── okapi-secret.yaml
```

Commit them and let flux pick up the changes. You should be able to see that the Okapi Hooks job completed and enabled the reshare software on your tenant. Check the enabled software on the new rs1 tenant:

```
http $okapi/_/proxy/tenants/rs1/modules
```

### UI Build
To build the UI, change into the `repos/reshare-ui` directory, and run:
```
yarn install
```

Since UI modules also have module descritors, we need to post the descriptors for the UI mods to Okapi. From the reshare-ui repo, run:
```
yarn build-module-descritprs
```
This will build a module descriptor for each UI module in the ModuleDescriptors directory. Change into the ModuleDescritpors directory and post them to Okapi:
```
for f in project*; do cat $f | http POST $okapi/_/proxy/modules "x-okapi-token:$token"; done
```

### UI Nginx container

### Create admin for ReShare Tenant

 -------------------------- WIP ----------------------------

## Appendix

### Run a debug pod
You can run a pod in your cluster to get a shell for debugging. For example:
```
kubectl -n reshare-dev run --rm -it --restart=Never debug --image=alpine:latest sh
```
This will start a temporary alpine linux image. You can add software by running `apk update` and then `apk add httpie` for example to add a specific package. From here you can reach okapi: `http http://okapi:9130`.

### HTTPpie
This document uses HTTPie as the command line http client for examples. Curl or another option could be used as well. More information about HTTPie is here: https://httpie.io/cli.
