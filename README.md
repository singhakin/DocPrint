3. Confluence DocumentationCopy the following sections directly into your wiki tool.I. Architecture OverviewRole: The Print Service acts as a secure middleware between the User Portal and the Print Factory.Security Model: "Verify then Process". No file reaches the conversion engine (Gotenberg) until the External AV Service returns a 200 OK / Clean status.Font Strategy: We use Metric-Compatible open-source fonts to ensure zero layout shift for Microsoft Office documents without requiring Microsoft licenses.Calibri $\rightarrow$ CarlitoCambria $\rightarrow$ CaladeaArial $\rightarrow$ Liberation SansII. Environment Variables

4. Variable,Description,Default
GOTENBERG_URL,Internal URL of the conversion container,http://gotenberg:3000/...
EXTERNAL_AV_URL,Endpoint of the Security Team's scanner,https://av-service...
DB_CONNECTION,SQL Connection String for analytics,sqlite:///...

III. Database Schema (Analytics)
Used for the "Daily Fidelity Report".

CREATE TABLE document_analytics (
    job_id UUID PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    filename VARCHAR(255),
    av_status VARCHAR(50), -- 'CLEAN' or 'INFECTED'
    font_fidelity VARCHAR(50), -- 'EXACT_MATCH' or 'SAFE_SUBSTITUTION'
    missing_fonts TEXT[] -- List of fonts requested but not found
);


IV. Troubleshooting Fonts
If a customer complains about layout issues:

Check the document_analytics table for their Job ID.

If fidelity_status is SAFE_SUBSTITUTION, the layout should be fine (metric match).

If missing_fonts contains a specific designer font (e.g., "Gotham-Bold"), advise the customer to Embed Fonts in their source file or upload a PDF directly.
