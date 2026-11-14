"""Download the court's official sitemap (the machine-readable index its robots.txt points to)."""
import re, sys, time, urllib.request, os
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (fedcir-panel-research)"}
get = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read().decode("utf-8", "replace")
index = get("https://www.cafc.uscourts.gov/sitemap_index.xml")
maps = [m for m in re.findall(r"<loc>([^<]+)</loc>", index) if "post-sitemap" in m]
urls = []
for m in maps:
    s = get(m); open(os.path.join(out, m.rsplit("/", 1)[1]), "w").write(s)
    urls += re.findall(r"<loc>([^<]+)</loc>", s); time.sleep(1)
open(os.path.join(out, "all_post_urls.txt"), "w").write("\n".join(urls))
print(len(maps), "sitemap files,", len(urls), "posting URLs")
