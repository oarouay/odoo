/** @odoo-module **/

// Import useRef
import { Component, useState, onWillStart, markup, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Removes potential markdown code block markers (```html ... ```) from a string.
 * @param {string} htmlString The raw string potentially containing markers.
 * @returns {string} The cleaned HTML string.
 */
function stripCodeBlockMarkers(htmlString) {
    if (typeof htmlString !== "string") {
        return "";
    }
    let cleaned = htmlString.trim();
    cleaned = cleaned.replace(/^```html\s*/i, '');
    cleaned = cleaned.replace(/```\s*$/, '');
    return cleaned.trim();
}

export class AIReportWizard extends Component {
    static template = "ai_mailing.AIReportWizard";
    static props = {
        close: Function,
        primaryCampaignId: { type: [Number, Boolean], optional: true },
        comparisonCampaignId: { type: [Number, Boolean], optional: true },
    };

    setup() {
        this.state = useState({
            loading: true,
            reportHtml: "",
            errorMessage: null,
        });

        this.orm = useService("orm");
        // Create a ref for the report content element
        this.reportContentRef = useRef("reportContent");

        onWillStart(async () => {
            await this.loadReport();
        });
    }

    async loadReport() {
        this.state.loading = true;
        this.state.errorMessage = null;
        const domain = this.props.primaryCampaignId ? [["id", "=", this.props.primaryCampaignId]] : [];
        const comparison_campaign_id = this.props.comparisonCampaignId || null;

        try {
            const result = await this.orm.call(
                "marketing.campaign",
                "generate_gemini_dashboard_report",
                [],
                {
                    domain: domain,
                    comparison_campaign_id: comparison_campaign_id,
                }
            );
            this.state.reportHtml = markup(stripCodeBlockMarkers(result));
        } catch (error) {
            console.error("Error generating AI report:", error);
            this.state.errorMessage = error.message || "An unknown error occurred while generating the report.";
            this.state.reportHtml = markup(`<div class="alert alert-danger" role="alert">Failed to load report: ${this.state.errorMessage}</div>`);
        } finally {
            this.state.loading = false;
        }
    }
    _onPrintReport() {
        // Access the element using the ref
        const reportContentElement = this.reportContentRef.el;

        // Add a check to ensure the element exists before proceeding
        if (!reportContentElement) {
            console.error("Could not find the referenced element 'reportContent' to print.");
            return;
        }

        const printContents = reportContentElement.innerHTML;
        const printWindow = window.open('', '', 'height=700,width=900');
        printWindow.document.write(printContents);
        printWindow.document.close();
        printWindow.focus();

        setTimeout(() => {
            try {
                printWindow.print();
                printWindow.close();
            } catch (e) {
                console.error("Error during printing:", e);
                printWindow.close();
            }
        }, 300);
    }
}
