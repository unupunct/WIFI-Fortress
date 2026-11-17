"""Build a Debian .deb from a staged tree, in Debian's own format (zstd)."""
import io, os, sys, tarfile
import zstandard as zstd

stage, out_path = sys.argv[1], sys.argv[2]

def add_tree(tf, root, modes, prefix=""):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel_dir = os.path.relpath(dirpath, root)
        for name in sorted(filenames) + sorted(dirnames):
            full = os.path.join(dirpath, name)
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            rel = rel.replace(os.sep, "/")
            info = tf.gettarinfo(full, arcname=prefix + rel)
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            if os.path.isdir(full):
                info.mode = 0o755
                tf.addfile(info)
            else:
                info.mode = 0o644 if rel == "control" else (
                    0o755 if (prefix + rel) in modes else 0o644)
                with open(full, "rb") as fh:
                    tf.addfile(info, fh)

def tar_of(root, modes):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        add_tree(tf, root, modes)
    return buf.getvalue()

# data: /opt and /usr
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
    add_tree(tf, os.path.join(stage, "opt"), {"opt/wifi-fortress/run.py"},
             prefix="opt/")
    add_tree(tf, os.path.join(stage, "usr"), {"usr/bin/wifi-fortress",
                                              "usr/share/applications/wifi-fortress.desktop"},
             prefix="usr/")
data = buf.getvalue()
control = tar_of(os.path.join(stage, "DEBIAN"),
                 {"control", "postinst", "prerm", "postrm"})

cctx = zstd.ZstdCompressor(level=19, write_checksum=False)
out = io.BytesIO()
out.write(b"!<arch>\n")
for name, payload in (("debian-binary", b"2.0\n"),
                      ("control.tar.zst", cctx.compress(control)),
                      ("data.tar.zst", cctx.compress(data))):
    out.write(f"{name:<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(payload):<10}`\n".encode("ascii"))
    out.write(payload)
    if len(payload) % 2:
        out.write(b"\n")
open(out_path, "wb").write(out.getvalue())
print("wrote", out_path, len(out.getvalue()), "bytes")
