#!/bin/bash

# Created by argbash-init v2.10.0
# Run 'argbash --strip user-content "source/bacchus-parsing.m4" -o "scripts/bacchus-parsing.sh"' to generate the 'bacchus2-parsing.sh' file.
# If you need to make changes later, edit 'bacchus2-parsing.sh' directly, and regenerate by running
# 'argbash --strip user-content "scripts/bacchus-parsing.sh" -o "scripts/bacchus-parsing.sh"'
script_dir=$(dirname "$_")/scripts
source "${script_dir}/bacchus-parsing.sh" || { echo "Couldn't find 'bacchus-parsing.sh' parsing library in the '$script_dir' directory"; exit 1; }
# vvv  PLACE YOUR CODE HERE  vvv

PrintOptions()
{
  printf 'Source directory:                    %s\n' "$_arg_source"
  printf 'Destination directory:               %s\n' "$_arg_dest"
  printf 'Base name for archive:               %s\n' "$_arg_basename"
  printf 'Use ramdisk for intermediate dirs:   %s\n' "$_arg_ramdisk"

  if [ "$_arg_disablecompress" == "off" ]; then
    if [ "$_arg_compressdir" != "." ]; then
      printf 'Intermediate compression directory:  %s\n' "$_arg_compressdir"
    fi
  else
      printf 'Compression:                         disabled\n'
  fi

  if [ -z "$password" ]; then
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
      printf 'Password is:                         %s\n' "$password"
    fi
  fi
}

ConfirmStart()
{
  if [ "$_arg_confirm" == "on" ]; then
    read -rsp "Press enter to begin..." confirm
    printf '\n\n'
  fi
}

Backup()
{
  printf '\n'
  printf ' ====================================\n'
  printf '|| Running Bacchus backup operation ||\n'
  printf ' ====================================\n'
  PrintOptions
  if [ "$_arg_tardir" != "." ]; then
    printf 'Intermediate tar directory:          %s\n' "$_arg_tardir"
  fi
  printf 'Volume size for archive:             %s\n' "$_arg_volumesize"
  printf '\n'
  ConfirmStart
  "${script_dir}"/bacchus-backup.sh "$_arg_source" "$_arg_dest" "$_arg_basename" "$_arg_tardir" "$_arg_compressdir" "$_arg_volumesize"
}

Restore()
{
  printf '\n'
  printf ' =====================================\n'
  printf '|| Running Bacchus restore operation ||\n'
  printf ' =====================================\n'
  PrintOptions
  if [ "$_arg_decryptdir" != "." ]; then
    printf 'Intermediate decryption directory:   %s\n' "$_arg_decryptdir"
  fi
  printf '\n'
  ConfirmStart
  "${script_dir}"/bacchus-restore.sh "$_arg_source" "$_arg_dest" "$_arg_basename" "$_arg_decryptdir" "$_arg_compressdir"
}

if [ -n "$_arg_filepassword" ]; then
  password=$(< "$_arg_filepassword")

elif [ -n "$_arg_commandpassword" ]; then
    password="$_arg_commandpassword"

elif [ "$_arg_userpassword" == "on" ]; then
  while true; do
    printf '\n'
    read -rsp "Enter a password for encryption or press enter for no password: " password
    printf '\n'
    if [ -n "$password" ]; then
      read -rsp "Re-enter a password for encryption or press enter for no password: " verify
      printf '\n'
      if [ -z "$verify" ] || [ "$password" != "$verify" ]; then
        printf 'Passwords do not match!\n'
      else
        break
      fi
    else
      break
    fi
  done
fi

BCS_PASSWORD="$password"
BCS_VERBOSETAR="$_arg_verbosetar"

export BCS_PASSWORD
export BCS_VERBOSETAR

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
