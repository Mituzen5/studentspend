#!/bin/sh
# Builds the drag-and-drop Netlify folder: ./netlify-site
# Usage: sh deploy/make_netlify_site.sh https://YOUR-USERNAME.pythonanywhere.com
BACKEND="${1:-https://YOUR-USERNAME.pythonanywhere.com}"
rm -rf netlify-site && mkdir -p netlify-site
cp -r static netlify-site/static && cp static/index.html netlify-site/index.html
cat > netlify-site/_redirects <<R
/api/*    $BACKEND/api/:splat    200!
/healthz  $BACKEND/healthz       200!
R
cat > netlify-site/_headers <<'H'
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: same-origin
  Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
H
echo "Built netlify-site/ -> backend $BACKEND"
