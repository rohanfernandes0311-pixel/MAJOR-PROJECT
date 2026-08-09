import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";

export default function ProtectedRoute({ children, role = null }) {
  const { authenticated, loading, ready, profile } = useAuth();
  if (loading || !ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="loader">Loading...</div>
      </div>
    );
  }
  if (!authenticated) return <Navigate to="/login" replace />;
  if (role && String(profile?.role || "").toLowerCase() !== String(role).toLowerCase()) {
    // unauthorized - redirect to home
    return <Navigate to="/" replace />;
  }
  return children;
}
