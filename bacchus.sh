#!/bin/bash

# Created by argbash-init v2.10.0
# Run 'argbash --strip user-content "source/bacchus-parsing.m4" -o "scripts/bacchus-parsing.sh"' to generate the 'bacchus2-parsing.sh' file.
# If you need to make changes later, edit 'bacchus2-parsing.sh' directly, and regenerate by running
# 'argbash --strip user-content "scripts/bacchus-parsing.sh" -o "scripts/bacchus-parsing.sh"'
script_dir=$(dirname "$_")/scripts
source "${script_dir}/bacchus-parsing.sh" || { echo "Couldn't find 'bacchus-parsing.sh' parsing library in the '$script_dir' directory"; exit 1; }
# vvv  PLACE YOUR CODE HERE  vvv

export BCS_SOURCE="$_arg_source"
export BCS_DEST="$_arg_dest"
export BCS_BASENAME="$_arg_basename"
export BCS_VOLUMESIZE="$_arg_volumesize"
export BCS_RAMDISK="$_arg_ramdisk"
export BCS_TARDIR="$_arg_tardir"
export BCS_COMPRESDIR="$_arg_compressdir"
export BCS_COMPRESS="$_arg_compress"
export BCS_DECRYPTDIR="$_arg_decryptdir"
export BCS_VERBOSETAR="$_arg_verbosetar"
export BCS_PASSWORD="$password"
export BCS_LOWDISKSPACE=2

PrintOptions()
{
  printf 'Source directory:                    %s\n' "$BCS_SOURCE"
  printf 'Destination directory:               %s\n' "$BCS_DEST"
  printf 'Base name for archive:               %s\n' "$BCS_BASENAME"
  if [ "$BCS_COMPRESS" == "on" ] || [ -n "$BCS_PASSWORD" ]; then
    printf 'Use ramdisk for intermediate dirs:   %s\n' "$BCS_RAMDISK"
  else
    printf 'Use ramdisk for intermediate dirs:   disabled\n'
  fi

  if [ "$BCS_COMPRESS" == "on" ] && [ "$BCS_RAMDISK" == "off" ]; then
    printf 'Intermediate compression directory:  %s\n' "$BCS_COMPRESDIR"
  fi
  if [ "$BCS_COMPRESS" == "off" ]; then
    printf 'Compression:                         disabled\n'
  fi

  if [ -z "$BCS_PASSWORD" ]; then
      printf 'Encryption:                          disabled\n'
  else
    if [ -n "$_arg_filepassword" ]; then
      printf 'Password, file-based:                %s\n' "$_arg_filepassword"
    elif [ -n "$_arg_commandpassword" ]; then
      printf 'Password:                            command-line\n'
    elif [ "$_arg_userpassword" == "on" ]; then
      printf 'Password:                            console from user\n'
    fi

    if [ "$_arg_revealpassword" == "on" ]; then
      printf 'Password is:                         %s\n' "$BCS_PASSWORD"
    fi
  fi
}

ConfirmStart()
{
  if [ "$_arg_confirm" == "on" ]; then
    read -rsp "Press enter to begin..." confirm
    printf '\n\n'
  fi
  if [ "$BCS_COMPRESS" == "off" ] || [ -z "$BCS_PASSWORD" ]; then
    BCS_RAMDISK="off"
  fi
}

Backup()
{
  printf '\n'
  printf ' ====================================\n'
  printf '|| Running Bacchus backup operation ||\n'
  printf ' ====================================\n'
  PrintOptions
  if [ "$BCS_RAMDISK" == "off" ] && ([ "$BCS_COMPRESS" == "on" ] || [ -n "$BCS_PASSWORD" ]); then
    printf 'Intermediate tar directory:          %s\n' "$BCS_TARDIR"
  fi
  printf 'Volume size for archive:             %s\n' "$BCS_VOLUMESIZE"
  printf '\n'
  ConfirmStart
  "${script_dir}"/bacchus-backup.sh
}

Restore()
{
  printf '\n'
  printf ' =====================================\n'
  printf '|| Running Bacchus restore operation ||\n'
  printf ' =====================================\n'
  PrintOptions
  if [ -n "$BCS_PASSWORD" ] && [ "$BCS_RAMDISK" == "off" ]; then
    printf 'Intermediate decryption directory:   %s\n' "$BCS_DECRYPTDIR"
  fi
  printf '\n'
  ConfirmStart
  "${script_dir}"/bacchus-restore.sh
}

if [ -n "$_arg_filepassword" ]; then
  BCS_PASSWORD=$(< "$_arg_filepassword")

elif [ -n "$_arg_commandpassword" ]; then
    BCS_PASSWORD="$_arg_commandpassword"

elif [ "$_arg_userpassword" == "on" ]; then
  while true; do
    printf '\n'
    read -rsp "Enter a password for encryption or press enter for no password: " BCS_PASSWORD
    printf '\n'
    if [ -n "$BCS_PASSWORD" ]; then
      read -rsp "Re-enter a password for encryption or press enter for no password: " verify
      printf '\n'
      if [ -z "$verify" ] || [ "$BCS_PASSWORD" != "$verify" ]; then
        printf 'Passwords do not match!\n'
      else
        break
      fi
    else
      break
    fi
  done
fi

case ${_arg_subcommand} in
  backup)
    Backup
    ;;
  restore)
    Restore
    ;;
  *)
    print_help
    printf 'FATAL ERROR: Required subcommand "backup" or "restore" not present\n'
    exit 1
    ;;
esac
# ^^^  TERMINATE YOUR CODE BEFORE THE BOTTOM ARGBASH MARKER  ^^^
