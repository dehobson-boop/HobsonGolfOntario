"""
scrape.py — fetches all Ontario course pages from UnderPar and writes data.json
Run locally or via GitHub Actions daily.
"""

import requests, json, re, time
from bs4 import BeautifulSoup
from datetime import datetime, timezone

ONTARIO_URL = "https://www.underpar.com/courses/canada/ontario"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://www.underpar.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# Fixed coordinate data (doesn't change)
COORDS = {
    "grand-valley-golf-country-club":          {"lat": 43.3557, "lng": -80.3987},
    "olivers-nest-golf-club":                  {"lat": 44.3396, "lng": -78.8619},
    "golfers-dream-golf-club":                 {"lat": 44.0359, "lng": -78.9799},
    "cardinal-18":                             {"lat": 44.2918, "lng": -78.7882},
    "lyndhurst-golf-course":                   {"lat": 44.2567, "lng": -79.3452},
    "wolf-run-golf-club":                      {"lat": 44.2198, "lng": -78.7610},
    "big-cedar-golf-country-club":             {"lat": 44.2965, "lng": -79.5329},
    "marlwood-golf-country-club":              {"lat": 44.5112, "lng": -79.9926},
    "cedarhurst-golf-club":                    {"lat": 44.4042, "lng": -79.1591},
    "lindsay-golf-country-club":               {"lat": 44.3385, "lng": -78.7247},
    "western-trent-golf-club":                 {"lat": 44.5361, "lng": -79.0747},
    "foxbridge-golf-course":                   {"lat": 44.1041, "lng": -79.0933},
    "the-club-at-westlinks":                   {"lat": 44.4270, "lng": -81.3725},
    "cobble-beach":                            {"lat": 44.6732, "lng": -80.9195},
    "mitchell-golf-country-club":              {"lat": 43.4811, "lng": -81.1983},
    "port-dover-golf-club":                    {"lat": 42.8154, "lng": -80.2383},
    "the-oaks-of-cobden":                      {"lat": 45.6133, "lng": -76.8446},
    "silver-lakes-golf-and-country-club":      {"lat": 44.1421, "lng": -79.5077},
    "southern-pines-golf-club":                {"lat": 43.1531, "lng": -79.9116},
    "kirby-links-golf-course-driving-range":   {"lat": 43.8904, "lng": -79.5284},
    "rainbow-ridge-golf-course":               {"lat": 45.7291, "lng": -81.8082},
    "willow-ridge-golf-and-country-club":      {"lat": 42.3229, "lng": -81.9684},
    "wildwood-golf-rv-resort":                 {"lat": 42.1435, "lng": -82.9522},
    "willow-tree-golf":                        {"lat": 42.9681, "lng": -81.6073},
    "black-bear-ridge":                        {"lat": 44.2486, "lng": -77.3922},
    "the-greens-at-renton":                    {"lat": 42.8745, "lng": -80.2307},
    "turnberry-golf-club":                     {"lat": 43.7228, "lng": -79.7740},
    "dalewood-golf-club":                      {"lat": 43.9953, "lng": -78.2541},
    "brockville-country-club":                 {"lat": 44.5751, "lng": -75.7087},
    "loyalist-country-club":                   {"lat": 44.1904, "lng": -76.7837},
    "bellmere-winds-golf-resort":              {"lat": 44.2641, "lng": -78.0997},
    "bowmanville-golf-and-country-club":       {"lat": 43.9501, "lng": -78.7082},
    "northern-dunes-golf-club":                {"lat": 44.6425, "lng": -81.1293},
    "golflive-health-fitness-club":            {"lat": 43.7732, "lng": -79.6184},
    "st-marys-golf-country-club-golf-only":    {"lat": 43.2624, "lng": -81.1175},
    "crestwood-golf-club":                     {"lat": 44.2500, "lng": -78.9608},
}


def fetch(url, retries=3):
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=15)
            if r.status_code == 200:
                return r.text
            print(f"  HTTP {r.status_code} for {url}")
        except Exception as e:
            print(f"  Error {url}: {e}")
        time.sleep(2 ** i)
    return None


def parse_listing_page(html):
    """Extract course slugs and basic info from the Ontario listing page."""
    soup = BeautifulSoup(html, "html.parser")
    courses = []

    for a in soup.find_all("a", href=re.compile(r"/courses/[^/]+$")):
        href = a["href"]
        slug = href.rstrip("/").split("/")[-1]
        # Skip non-course links
        if slug in ("canada", "ontario", "") or "/" in slug:
            continue
        if slug not in courses:
            courses.append(slug)

    return list(dict.fromkeys(courses))  # deduplicate preserving order


def parse_course_page(html, slug):
    """Extract name, image, price, deal info from a single course page."""
    soup = BeautifulSoup(html, "html.parser")

    # Image from og:image
    og_img = soup.find("meta", property="og:image")
    image = og_img["content"].strip() if og_img and og_img.get("content") else None

    # Name from og:title or h1
    og_title = soup.find("meta", property="og:title")
    h1 = soup.find("h1")
    name = ""
    if og_title and og_title.get("content"):
        # Strip " - UnderPar Golf Deals" suffix
        name = re.sub(r"\s*[-|].*?(Golf Deals|UnderPar).*$", "", og_title["content"], flags=re.IGNORECASE).strip()
    elif h1:
        name = h1.get_text(strip=True)

    # Price — look for CDN $ amounts
    prices = re.findall(r"CDN\s*\$\s*([\d,]+(?:\.\d{2})?)", html)
    price = float(prices[0].replace(",", "")) if prices else None

    # Rack rate — "Retail Price $XX" or "Rack Rate Value: CDN $XX"
    rack_match = re.search(r"(?:Retail Price|Rack Rate Value)[^\$]*\$\s*([\d,]+(?:\.\d{2})?)", html)
    rack = float(rack_match.group(1).replace(",", "")) if rack_match else None

    # % off
    off = 0
    if price and rack and rack > price:
        off = round((rack - price) / rack * 100)

    # Location city — from description or address
    loc_match = re.search(r"([A-Za-z\s]+),\s*ON", html)
    loc = loc_match.group(1).strip() if loc_match else ""

    # Stay & Play flag
    stay = bool(re.search(r"stay.{0,10}play|night.{0,20}stay", html, re.IGNORECASE))

    # Simulator flag
    sim = bool(re.search(r"simulat", html, re.IGNORECASE))

    # Deal summary line — first bullet point content
    deal_match = re.search(r"((?:\d+)\s*Holes?[^<\n]{0,80})", html, re.IGNORECASE)
    deal = deal_match.group(1).strip() if deal_match else ""

    coords = COORDS.get(slug, {"lat": 44.0, "lng": -79.5})

    return {
        "slug": slug,
        "name": name,
        "loc": loc,
        "lat": coords["lat"],
        "lng": coords["lng"],
        "price": price,
        "rack": rack,
        "off": off,
        "deal": deal,
        "image": image,
        "stay": stay,
        "sim": sim,
        "url": f"https://www.underpar.com/courses/{slug}",
    }


def main():
    print(f"Fetching Ontario listing page...")
    listing_html = fetch(ONTARIO_URL)
    if not listing_html:
        print("Failed to fetch listing page — aborting.")
        return

    slugs = parse_listing_page(listing_html)

    # Fall back to known slugs if scrape returns nothing useful
    if len(slugs) < 5:
        slugs = list(COORDS.keys())

    print(f"Found {len(slugs)} course slugs")

    courses = []
    for slug in slugs:
        url = f"https://www.underpar.com/courses/{slug}"
        print(f"  Fetching {slug}...")
        html = fetch(url)
        if html:
            course = parse_course_page(html, slug)
            if course["name"]:
                courses.append(course)
                print(f"    -> {course['name']} | ${course['price']} | {course['off']}% off | img: {'yes' if course['image'] else 'no'}")
        time.sleep(0.5)  # be polite

    output = {
        "updated": datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC"),
        "courses": courses,
    }

    with open("data.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(courses)} courses to data.json")
    print(f"Images found: {sum(1 for c in courses if c['image'])}/{len(courses)}")


if __name__ == "__main__":
    main()
