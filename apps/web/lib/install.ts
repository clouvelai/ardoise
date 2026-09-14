export const INSTALL_TAG = "v0.3.2";
export const INSTALL_SHA256 =
  "fabc5874b1befdc3e1fe0e9edbb70f82bdbffcbf9297d2df39a1866361e0ff88";
export const INSTALL_SCRIPT_URL = `https://raw.githubusercontent.com/clouvelai/ardoise/${INSTALL_TAG}/install.sh`;
export const INSTALL_RELEASE_URL = `https://github.com/clouvelai/ardoise/releases/tag/${INSTALL_TAG}`;
export const INSTALL_ONE_LINER = `curl -fsSL ${INSTALL_SCRIPT_URL} | sh`;
export const INSTALL_VERIFY = [
  `curl -fsSL ${INSTALL_SCRIPT_URL} -o install.sh`,
  `echo "${INSTALL_SHA256}  install.sh" | shasum -a 256 -c -`,
  "chmod +x install.sh && ./install.sh",
].join("\n");
