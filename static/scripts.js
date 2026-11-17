document.addEventListener("DOMContentLoaded", function () {

    console.log("Trust & Scam Alert Loaded");

    // Search form
    const searchForm = document.getElementById("searchForm");

    if (searchForm) {
        searchForm.addEventListener("submit", function () {
            console.log("Searching...");
        });
    }

    // Report form
    const reportForm = document.getElementById("reportForm");

    if (reportForm) {
        reportForm.addEventListener("submit", function () {
            alert("Report submitted successfully!");
        });
    }

});
