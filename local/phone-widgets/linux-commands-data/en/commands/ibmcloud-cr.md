# TAGLINE

manages IBM Cloud Container Registry

# TLDR

**Login to registry**

```ibmcloud cr login```

**List images**

```ibmcloud cr image-list```

**Create namespace**

```ibmcloud cr namespace-add [namespace]```

**Build image**

```ibmcloud cr build -t [registry/namespace/image:tag] [.]```

**Remove image**

```ibmcloud cr image-rm [image]```

**List namespaces**

```ibmcloud cr namespace-list```

# SYNOPSIS

**ibmcloud cr** _command_ [_options_]

# PARAMETERS

_COMMAND_
> Container Registry command.

**login**
> Log the local Docker daemon in to the IBM Cloud registry.

**image-list**
> List images in your account/namespaces.

**image-rm** _IMAGE_
> Remove one or more images from the registry.

**image-tag** _SRC_ _DST_
> Add a new tag to an existing image.

**namespace-add** _NAME_
> Create a namespace.

**namespace-list**
> List namespaces in the targeted account.

**namespace-rm** _NAME_
> Delete a namespace (must be empty).

**build** _CONTEXT_
> Build a container image with IBM Cloud's remote builder and push the result.

**va** _IMAGE_
> Show Vulnerability Advisor results for an image.

**quota**
> Display storage and pull-traffic quota for the account.

**region-set** _REGION_
> Switch the registry region (e.g., _us-south_, _eu-de_, _jp-tok_).

**--help**
> Display help information.

# DESCRIPTION

**ibmcloud cr** manages IBM Cloud Container Registry. It provides private Docker image storage and vulnerability scanning.

The tool handles namespaces, images, and registry authentication. It integrates with IBM Cloud Kubernetes Service.

# CAVEATS

Registry plugin required. Namespace quotas apply. Vulnerability scanning available.

# HISTORY

ibmcloud cr is the Container Registry plugin for **IBM Cloud** CLI.

# SEE ALSO

[ibmcloud](/man/ibmcloud)(1), [docker](/man/docker)(1), [ibmcloud-ks](/man/ibmcloud-ks)(1)
