function view(text, now, vertical) {
    var glyph="\uF09B";
    var none={state:"none",label:glyph,tooltip:"Open GitHub Actions to load",
        accessible:"Open GitHub Actions to load",active:false,dimmed:true,recheckAt:0};
    var status;
    try { status=JSON.parse(text); } catch (error) { return none; }
    if (!status || status.version !== 1 || !["none","ok","stopped","rate"].includes(status.state)) return none;
    function count(value) {
        var n=Number(value);
        return isFinite(n) ? Math.max(0,Math.floor(n)) : 0;
    }
    function clock(t) {
        var d=new Date(t);
        return ("0"+d.getHours()).slice(-2)+":"+("0"+d.getMinutes()).slice(-2);
    }
    var running=count(status.running), failed=count(status.failed);
    var countsAt=count(status.countsAt), cooldownUntil=count(status.cooldownUntil);
    var reason=typeof status.reason==="string" ? status.reason.slice(0,120) : "";
    var account=typeof status.account==="string" ? status.account.slice(0,100) : "";
    var state=status.state;
    if (state==="rate" && cooldownUntil<=now) state=countsAt>0 ? "ok" : "none";
    if (state==="none") return none;
    var parts=[glyph];
    if (state==="stopped") parts.push("!");
    else {
        if (running>0) parts.push("●"+running);
        if (failed>0) parts.push("✕"+failed);
    }
    var lines=[];
    if (state==="stopped") lines.push("GitHub Actions stopped"+(reason ? ": "+reason : "")+". Open the panel to fix it.");
    else {
        if (state==="rate") lines.push("GitHub paused until "+clock(cooldownUntil));
        if (state==="ok" || countsAt>0) {
            lines.push("GitHub Actions"+(account ? " · "+account : ""));
            lines.push(running+" running "+(running===1 ? "workflow run" : "workflow runs")+", "+failed+" failing "+(failed===1 ? "repository" : "repositories"));
            if (countsAt>0) lines.push("Last repository activity read at "+clock(countsAt)+"; watched runs are checked every 30 s, slower when the quota is low");
        }
    }
    return {state:state,label:parts.join(vertical ? "\n" : " "),tooltip:lines.join("\n"),
        accessible:lines.join(", "),active:state==="stopped" || failed>0,
        dimmed:state==="rate",recheckAt:state==="rate" ? cooldownUntil : 0};
}
