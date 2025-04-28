/** @odoo-module */

import { registry } from "@web/core/registry"
import { KpiCard } from "./kpi_card/kpi_card";
import { ChartRenderer} from "./chart_renderer/chart_renderer";
import { _t } from "@web/core/l10n/translation";
import { useService} from "@web/core/utils/hooks";
import {AIReportWizard} from "./wizard/wizard_report";

const { Component, onWillStart, useRef, onMounted, useState } = owl

export class OwlSalesDashboard extends Component {
    setup() {
        this.state = useState({
            showAIReportModal: false,
            selectedCampaignId: null,
            comparisonCampaignId : null,
            chartInterval: 'day',
            chartDateRange: 30,
            socialMediaDateRange: 30,
            total_clicks:{
                value: 0,
                percentage:0
            },
            total_revenue:{
                value: 0,
                percentage:7
            },
            total_sales:{
                value: 0,
                percentage:0
            },
            conversion_rate:{
                value: 0,
                percentage:0
            },
            avg_order:{
                value: 0,
                percentage:0
            },
            unique_clicks:{
                value: 0,
                percentage:0
            },
            roi:{
                value: 0 + '%',
                percentage: 0
            },
            cpc:{
                value: '$' + 0,
                percentage: 0
            },
            cpa:{
                value: '$' + 0,
                percentage: 0
            },
            campaigns: []
        })
        this.orm = useService("orm")
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.primaryCampaignSelectRef = useRef("primaryCampaignSelect");
        this.comparisonCampaignSelectRef = useRef("comparisonCampaignSelect");

        onWillStart(async () => {
            await this.loadCampaigns();
            await this.loadDashboardData();
        });
    }

    async loadCampaigns() {
        try {
            const campaigns = await this.orm.call(
                "marketing.campaign",
                "search_read",
                [[]],
                {
                    fields: ["name", "start_date", "end_date", "status"],
                    order: "start_date desc",
                }
            );
            this.state.campaigns = campaigns;
        } catch (error) {
            console.error("Error loading campaigns:", error);
        }
    }

    async loadDashboardData() {



        try {
            const domain = this.state.selectedCampaignId ? [['id', '=', this.state.selectedCampaignId]] : [];
            console.log("Loading data with domain:", domain);

            const params = [domain];
            if (this.state.comparisonCampaignId) {
                params.push(this.state.comparisonCampaignId);
                console.log("ousama",this.state.comparisonCampaignId);  // comparison_campaign_id
            }

            const data = await this.orm.call(
                "marketing.campaign",
                "get_dashboard_metrics",
                params
            );
            console.log("Received dashboard data:", data);

            // Update state with new values
            this.state.total_clicks.value = data.total_clicks;
            this.state.total_clicks.percentage = data.clicks_change_percent || 0;

            this.state.total_revenue.value = data.total_revenue;
            this.state.total_revenue.percentage = data.revenue_change_percent || 0;

            this.state.total_sales.value = data.total_sales;
            this.state.total_sales.percentage = data.sales_change_percent || 0;

            this.state.conversion_rate.value = data.conversion_rate;
            this.state.conversion_rate.percentage = data.conversion_rate_change_percent || 0;

            this.state.avg_order.value = '$' + data.avg_order;
            this.state.avg_order.percentage = data.avg_order_change_percent || 0;

            this.state.unique_clicks.value = data.unique_clicks;
            this.state.unique_clicks.percentage = data.unique_clicks_change_percent || 0;

            this.state.roi.value = data.roi + '%';
            this.state.roi.percentage = data.roi_change_percent || 0;

            this.state.cpc.value = '$' + data.cpc;
            this.state.cpc.percentage = data.cpc_change_percent || 0;

            this.state.cpa.value = '$' + data.cpa;
            this.state.cpa.percentage = data.cpa_change_percent || 0;



            console.log("Updated state:", this.state);
        } catch (error) {
            console.error("Error loading dashboard data:", error);
        }
    }

    onPrimaryCampaignChange(ev) {
        const selectedId = parseInt(ev.target.value);
        this.state.selectedCampaignId = selectedId || null;
        this.loadDashboardData();
        console.log("Selected Primary Campaign ID:", this.state.selectedCampaignId);
    }

    onComparisonCampaignChange(ev) {
        const selectedId = parseInt(ev.target.value);
        this.state.comparisonCampaignId = selectedId || null;
        this.loadDashboardData();
        console.log("Selected Comparison Campaign ID:", this.state.comparisonCampaignId);
    }
    onIntervalChange(ev) {
        this.state.chartInterval = ev.target.value;
    }

    onDateRangeChange(ev) {
        this.state.chartDateRange = parseInt(ev.target.value);
    }
    onSocialMediaDateRangeChange(ev) {
        this.state.socialMediaDateRange = parseInt(ev.target.value);
    }
    onBudgetDateRangeChange(ev) {
        this.state.budgetDateRange = parseInt(ev.target.value);
    }

    onGenerateReportClick() {
        if (!this.state.selectedCampaignId) {
            this.notification.add(_t("Please select a primary campaign first"), { type: "warning" });
            return;
        }
        this.dialog.add(AIReportWizard, {
            primaryCampaignId: this.state.selectedCampaignId,
            comparisonCampaignId: this.state.comparisonCampaignId,
            close: () => this.dialog.remove(),
        });
    }

    closeAIReportModal() {
        this.state.showAIReportModal = false;
    }


    static components = { KpiCard, ChartRenderer, AIReportWizard };
}

OwlSalesDashboard.template = "ai_mailing.OwlSalesDashboard"

registry.category("actions").add("ai_mailing.sales_dashboard", OwlSalesDashboard)