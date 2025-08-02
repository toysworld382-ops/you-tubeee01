import os
import sys
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory, Response
from src.routes.download import download_bp

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Register blueprints
app.register_blueprint(download_bp, url_prefix='/api')

@app.route('/')
def index():
    # Check if ads are enabled via environment variable
    ads_enabled = os.environ.get('ENABLE_ADS', 'false').lower() == 'true'
    if ads_enabled:
        return send_from_directory('static', 'index_with_ads.html')
    else:
        return send_from_directory('static', 'index.html')

@app.route('/about')
def about():
    return send_from_directory('static', 'about.html')

@app.route('/privacy')
def privacy():
    return send_from_directory('static', 'privacy.html')

@app.route('/terms')
def terms():
    return send_from_directory('static', 'terms.html')

@app.route('/contact')
def contact():
    return send_from_directory('static', 'contact.html')

@app.route('/ads.txt')
def ads_txt():
    """
    Ads.txt file for Google AdSense verification
    Replace the publisher ID with your actual AdSense publisher ID
    """
    adsense_publisher_id = os.environ.get('ADSENSE_PUBLISHER_ID', 'pub-XXXXXXXXXXXXXXXXX')
    ads_content = f"google.com, {adsense_publisher_id}, DIRECT, f08c47fec0942fa0"
    return Response(ads_content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap():
    """
    Generate sitemap for SEO
    """
    domain = os.environ.get('DOMAIN', 'https://your-domain.com')
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{domain}/</loc>
        <lastmod>2025-01-01</lastmod>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{domain}/about</loc>
        <lastmod>2025-01-01</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>{domain}/privacy</loc>
        <lastmod>2025-01-01</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>
    <url>
        <loc>{domain}/terms</loc>
        <lastmod>2025-01-01</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.6</priority>
    </url>
    <url>
        <loc>{domain}/contact</loc>
        <lastmod>2025-01-01</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.7</priority>
    </url>
</urlset>"""
    return Response(sitemap_content, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    """
    Robots.txt for search engine crawling
    """
    domain = os.environ.get('DOMAIN', 'https://your-domain.com')
    robots_content = f"""User-agent: *
Allow: /
Disallow: /api/
Disallow: /downloads/

Sitemap: {domain}/sitemap.xml"""
    return Response(robots_content, mimetype='text/plain')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8001))
    app.run(host='0.0.0.0', port=port, debug=False)

