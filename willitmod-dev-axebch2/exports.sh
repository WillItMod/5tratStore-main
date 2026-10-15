#!/usr/bin/env bash

# Match the group of this recipe's already-declared Docker socket. This file is
# sourced by Umbrel; preserve the caller's shell options and tolerate a missing
# or inaccessible socket without inventing host group access.
_axebch2_export_socket_group() {
  local socket_metadata socket_mode socket_gid
  unset AXEBCH2_DOCKER_GID
  [[ -S /var/run/docker.sock ]] || return 0
  socket_metadata="$(stat -c '%a:%g' /var/run/docker.sock 2>/dev/null)" || return 0
  socket_mode="${socket_metadata%%:*}"
  socket_gid="${socket_metadata#*:}"
  [[ "$socket_mode" =~ ^[0-7]{3,4}$ && "$socket_gid" =~ ^[0-9]+$ ]] || return 0
  (( (8#$socket_mode & 8#020) != 0 )) || return 0
  export AXEBCH2_DOCKER_GID="$socket_gid"
  return 0
}

_axebch2_export_socket_group
unset -f _axebch2_export_socket_group
