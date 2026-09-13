#!/bin/sh
# Copies the staged plugins, plugin list, and Dashboard into the record vault. Run only after Mike's hash of nu is done.
set -e
V=/home/mike/Desktop/nu/record
S=/tmp/claude-1000/-home-mike-Desktop-nu-curator-pass/83a15ca4-15db-459e-8771-7ccbca37328a/scratchpad/plugins
mkdir -p "$V/.obsidian/plugins"
for p in dataview juggl obsidian-charts timelines-revamped; do mkdir -p "$V/.obsidian/plugins/$p"; cp "$S/$p"/main.js "$S/$p"/manifest.json "$S/$p"/styles.css "$V/.obsidian/plugins/$p/"; done
cp "$S/community-plugins.json" "$V/.obsidian/community-plugins.json"
cp "$S/Dashboard.md" "$V/Wiki/Dashboard.md"
grep -q 'Dashboard' "$V/Wiki/Index.md" || sed -i 's|^## Reading groups$|## Dashboard\n\n- [[Dashboard]] -- live Dataview tables and a contributor chart\n\n## Reading groups|' "$V/Wiki/Index.md"
printf '\n## %s plugins\n\n- installed community plugins into .obsidian/plugins (local JavaScript, copied by hand, versions: dataview 0.5.68, juggl 1.5.0, obsidian-charts 3.9.0, timelines-revamped 2.4.0); wrote Wiki/Dashboard.md; Index updated\n' "$(date -Iseconds | cut -c1-19)" >> "$V/Wiki/Log.md"
echo "installed into $V/.obsidian/plugins:"; ls "$V/.obsidian/plugins"
