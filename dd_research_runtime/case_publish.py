"""Publish a verified staged case as a single rename.

POSIX lets ``os.replace`` rename one directory over another, so a case could be
published by creating the destination as an exclusive reservation and then
replacing it. Windows refuses that with ``PermissionError: [WinError 5]``
because a directory cannot replace an existing directory.

The identifier is therefore reserved in a separate file, and the staged
directory is renamed onto a name that does not exist yet, which both platforms
allow and treat as one atomic step. A crashed creation leaves either nothing or
a complete case plus one private reservation file, never a partial case.
"""

import os
from pathlib import Path


def reserve(workspace, case_id):
    """Claim a case identifier before its directory exists.

    The reservation file is created exclusively, so two writers that somehow
    chose the same identifier cannot both proceed.
    """
    reservation = Path(workspace) / ('.reserve-' + case_id)
    try:
        os.close(os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except FileExistsError:
        raise FileExistsError('This case identifier is already in use.') from None
    return reservation


def publish(staged, destination, reservation, *, fault=None):
    """Move a verified staged case into place as one rename.

    ``fault`` is the test hook the callers already use to simulate an
    interruption between steps.
    """
    destination = Path(destination)
    try:
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('A saved case already uses this identifier.')
        if fault is not None:
            fault('before_publication')
        os.replace(Path(staged), destination)
        if fault is not None:
            fault('after_publication')
        return destination
    finally:
        # A published case keeps its content; only the claim is removed.
        try:
            reservation.unlink()
        except OSError:
            pass
