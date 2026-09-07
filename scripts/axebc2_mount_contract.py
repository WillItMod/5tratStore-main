"""Resolve AxeBC2's strict mounts for release validation.

File-backed Compose configs are read-only Engine bind mounts. Local-driver
bind volumes do not create their host source directories. Neither representation
uses the short bind syntax that implicitly creates missing host paths.
"""


def effective_mounts(compose):
    mounts = []
    for service_name, service in compose["services"].items():
        for volume in service.get("volumes", []):
            if isinstance(volume, str):
                parts = volume.split(":")
                if len(parts) != 3:
                    raise ValueError(f"{service_name}: mount requires explicit nocopy mode")
                source, target, mode = parts
                modes = set(mode.split(","))
                readonly = "ro" in modes
                nocopy = "nocopy" in modes
                if modes - {"ro", "rw", "nocopy"}:
                    raise ValueError(f"{service_name}: unexpected mount mode")
                kind = "volume"
            else:
                kind = volume["type"]
                source, target = volume["source"], volume["target"]
                readonly = volume.get("read_only", False)
                nocopy = volume.get("volume", {}).get("nocopy", False)
            if kind == "bind":
                if volume.get("bind", {}).get("create_host_path") is not False:
                    raise ValueError(f"{service_name}: host bind must explicitly reject absent sources")
            elif kind == "volume":
                declaration = compose.get("volumes", {}).get(source, {})
                options = declaration.get("driver_opts", {})
                if declaration.get("driver") != "local" or declaration.get("external"):
                    raise ValueError(f"{service_name}: directory mount must use the local bind driver")
                if options.get("type") != "none" or options.get("o") != "bind" or not options.get("device"):
                    raise ValueError(f"{service_name}: local volume must bind its exact host directory")
                if not nocopy:
                    raise ValueError(f"{service_name}: image data must not populate host directories")
                source = options["device"]
            else:
                raise ValueError(f"{service_name}: unsupported mount type {kind}")
            mounts.append((service_name, source, target, bool(readonly)))
        for grant in service.get("configs", []):
            declaration = compose.get("configs", {}).get(grant["source"], {})
            if not declaration.get("file") or declaration.get("external"):
                raise ValueError(f"{service_name}: config must use an existing host file")
            mounts.append((service_name, declaration["file"], grant["target"], True))
    return sorted(mounts)
