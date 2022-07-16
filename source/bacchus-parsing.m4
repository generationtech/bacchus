#!/bin/bash

# m4_ignore(
echo "This is just a parsing library template, not the library - pass this file to 'argbash' to fix this." >&2
exit 11  #)Created by argbash-init v2.10.0
# ARG_POSITIONAL_SINGLE([subcommand], [backup or restore])
# ARG_OPTIONAL_SINGLE([source], [s], [source directory], [.])
# ARG_OPTIONAL_SINGLE([dest], [d], [destination directory], [.])
# ARG_OPTIONAL_SINGLE([basename], [b], [base filename for incremental archive filenames], [backupfile])
# ARG_OPTIONAL_SINGLE([volumesize], [v], [size in kB for each incremental archive file (only used for backup operations)], [100000])
# ARG_OPTIONAL_BOOLEAN([ramdisk], [r], [create ramdisk. If used, can ommit optional tardir, compressdir & decryptdir], on)
# ARG_OPTIONAL_SINGLE([tardir], [t], [intermediate directory where raw tar file is built], [.])
# ARG_OPTIONAL_SINGLE([compressdir], [c], [intermediate directory compression operations are performed], [.])
# ARG_OPTIONAL_BOOLEAN([compress], [z], [disable compression], on)
# ARG_OPTIONAL_SINGLE([decryptdir], [e], [intermediate directory for restore decryption operations], [.])
# ARG_OPTIONAL_BOOLEAN([userpassword], [u], [get optional password from user console for encryption or decryption], on)
# ARG_OPTIONAL_SINGLE([filepassword], [f], [get optional password from file for encryption or decryption **warning**])
# ARG_OPTIONAL_SINGLE([commandpassword], [p], [get optional password from command line for encryption or decryption **danger**])
# ARG_OPTIONAL_BOOLEAN([revealpassword], [R], [echo optional password on screen], off)
# ARG_OPTIONAL_BOOLEAN([verbosetar], [T], [show tar verbose], off)
# ARG_OPTIONAL_BOOLEAN([confirm], [C], [confirm before starting operation], on)
# ARG_OPTIONAL_BOOLEAN([estimate], [E], [estimate total time needed for operation], on)
# ARG_DEFAULTS_POS
# ARG_HELP([Bacchus is a backup/resture program using tar, pigz, and gpg for ad-hoc data backups])
# ARGBASH_SET_INDENT([  ])
# ARGBASH_SET_DELIM([ ])
# ARGBASH_GO
