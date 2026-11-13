# addonly

Put a file into a folder that you only ever add to: a release drop, a shared test folder,
a folder an agent may write to but must never clean up. addonly copies by exclusive create,
refuses linked folders, and proves afterwards that the folder changed by exactly one file.
Standard library only, one file of code.

```
pip install git+https://github.com/decentralizeallengineering/addonly
```

## 30-second tour

```
$ addonly check-zip app-1.4.2.zip --version-file VERSION
ok ed9eadcca75f0534d2fef44819bd6d522b73a1aa43eca600c1be7fb4bcf43e70 app-1.4.2.zip version 1.4.2
$ addonly put app-1.4.2.zip drop/
added ed9eadcca75f0534d2fef44819bd6d522b73a1aa43eca600c1be7fb4bcf43e70 drop/app-1.4.2.zip
$ addonly put app-1.4.2.zip drop/   # again
addonly: refused: target exists (file, folder or link): drop/app-1.4.2.zip
exit 3
$ addonly put bad.zip drop/ --zip-check
addonly: refused: member with a denied extension: app/model.pkl
exit 2
```

## What put promises

- No code path overwrites, renames, truncates or removes a file. The target is opened with
  `O_CREAT | O_EXCL | O_NOFOLLOW`; a target name that exists as a file, a folder or even a
  dangling link is refused (exit 3).
- The folder must exist and must not be a link or sit under one (exit 3). A target name
  with `/`, `.` or `..` is refused (exit 2).
- The folder is listed with sha256 before and after. If anything other than the one new
  file changed, exit 4. The new file's hash must equal the source's.

## check-zip

`addonly check-zip ZIP [--max-member BYTES] [--deny-ext .exe,.dll,.pkl,.pickle] [--version-file VERSION]`

Refuses (exit 2) a zip that does not open, has a bad CRC, a member over `--max-member`
(default 10 MiB), a member with a denied extension, or a member path that is absolute or
uses `..`. With `--version-file` the file must sit at the zip root or in one top folder and
hold a plain version (`[A-Za-z0-9._-]`, at most 64 characters). `put --zip-check` runs the
same checks before copying.

Exit codes: 0 done, 1 unexpected error (one line, no traceback), 2 input refused,
3 target exists or folder refused, 4 folder changed by more than the added file.
Python: `from addonly import put, check_zip`.

Not covered: two writers racing on the same folder can make put exit 4 after its own file
is written. The file stays; the exit code tells you to look.

## Tests

```
pip install -e ".[test]" && pytest
```

## Related

- [trash30](https://github.com/decentralizeallengineering/trash30): the other half, a trash folder that empties itself after 30 days
- [all tools](https://github.com/decentralizeallengineering): the index of this account

Licence: Apache-2.0.
