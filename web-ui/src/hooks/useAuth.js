import { useContext } from "react";
import { useAuth as useAuthContext } from "../authentication/AuthProvider";

export default function useAuth() {
  return useAuthContext();
}
