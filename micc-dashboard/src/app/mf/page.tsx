"use client";
import NavBar from "@/components/NavBar";
import MFPanel from "@/components/MFPanel";

export default function MFPage() {
  return (
    <div style={{minHeight:"100vh",background:"var(--bg)"}}>
      <NavBar />
            <div style={{padding:"16px 20px",maxWidth:1200,margin:"0 auto"}}>
        <div style={{fontFamily:"monospace",fontSize:14,fontWeight:700,
                     letterSpacing:"0.12em",color:"var(--bull)",marginBottom:14}}>
          MUTUAL FUND NAV TRACKER
        </div>
        <MFPanel />
      </div>
    </div>
  );
}
