# a4norm — photo of a document -> scanner-grade A4 PDF
#
# Nothing in the tool is macOS-specific: it is stdlib-only Python driving two
# ordinary CLI tools. Alpine is the base because its ImageMagick delegates are
# separate packages, so HEIC support is a line in the install list rather than a
# hope about how a distro happened to build its binary. (PNG needs no delegate
# package — it is in the base imagemagick build.)
FROM alpine:3.21

RUN apk add --no-cache \
      python3 \
      imagemagick \
      imagemagick-heic \
      imagemagick-jpeg \
      imagemagick-tiff \
      imagemagick-webp \
      poppler-utils

# No ghostscript on purpose. Alpine's ImageMagick has no PDF coder without it,
# and a4norm writes its own PDF — a JPEG per page plus a few hundred bytes of
# boilerplate — so the image stays at ImageMagick + poppler. ImageMagick never
# READS a PDF here either; poppler does that.

# Built from the plugin root so the skill's script is the only copy:
#   docker build -f docker/Dockerfile -t a4norm:1.1.0 .
COPY skills/scan/scripts/a4norm /usr/local/bin/a4norm
RUN chmod +x /usr/local/bin/a4norm

# Build-time smoke test: a synthetic page must survive the whole pipeline and
# come out as an A4 PDF, and HEIC must actually decode. A missing delegate is
# then a failed build instead of a surprise on someone's first real document.
RUN set -e; \
    magick -size 1200x1700 xc:white -fill '#111111' \
      -draw "rectangle 200,300 1000,346" -draw "rectangle 200,520 860,566" \
      -draw "rectangle 200,740 940,786" \
      -background '#8b8b8b' -rotate 0.6 -bordercolor '#8b8b8b' -border 40 \
      /tmp/smoke.jpg; \
    a4norm -o /tmp/smoke.pdf /tmp/smoke.jpg; \
    pdfinfo /tmp/smoke.pdf | grep -q 'A4'; \
    magick -list format | grep -qiE '^ +HEIC' || (echo "no HEIC delegate" && exit 1); \
    rm -f /tmp/smoke.jpg /tmp/smoke.pdf

WORKDIR /work
ENTRYPOINT ["a4norm"]
CMD ["--help"]
