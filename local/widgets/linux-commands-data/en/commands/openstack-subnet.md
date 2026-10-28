# TAGLINE

manages IP subnets within OpenStack networks

# TLDR

**List subnets**

```openstack subnet list```

**Create subnet**

```openstack subnet create --network [network] --subnet-range [192.168.1.0/24] [subnet_name]```

**Show subnet details**

```openstack subnet show [subnet_name]```

**Delete subnet**

```openstack subnet delete [subnet_name]```

# SYNOPSIS

**openstack subnet** _command_ [_options_]

# PARAMETERS

**list**
> List subnets.

**create** _name_
> Create subnet.

**delete** _name_
> Delete subnet.

**show** _name_
> Show subnet details.

**--network** _network_
> Parent network.

**--subnet-range** _cidr_
> IP address range in CIDR.

**--gateway** _ip_
> Gateway IP address.

**--dhcp** / **--no-dhcp**
> Enable or disable DHCP on the subnet (default: _enabled_).

**--dns-nameserver** _ip_
> DNS server address (repeat for multiple).

**--allocation-pool** _start=IP,end=IP_
> Restrict DHCP allocation to a range within the subnet (repeatable).

**--ip-version** _4|6_
> IP version of the subnet (default: _4_).

**--ipv6-address-mode** _MODE_
> IPv6 address mode: _slaac_, _dhcpv6-stateful_, or _dhcpv6-stateless_.

**--ipv6-ra-mode** _MODE_
> IPv6 router advertisement mode (same values as **--ipv6-address-mode**).

**--host-route** _destination=CIDR,gateway=IP_
> Add a static host route (repeatable).

**--subnet-pool** _NAME_
> Allocate the range from a subnet pool instead of specifying **--subnet-range** directly.

# DESCRIPTION

**openstack subnet** manages IP subnets within OpenStack networks. Configure IP ranges, DHCP, DNS, and routing for virtual networks. Part of OpenStack unified CLI.

# SEE ALSO

[openstack-network](/man/openstack-network)(1), [openstack-port](/man/openstack-port)(1)

