export const INSTALL_TAG = "v0.3.3";
export const INSTALL_SHA256 =
  "417344fac213bd1bf330227b754d96971920db4a47d5589f3fac7997d7ddeaa8";
export const INSTALL_SCRIPT_URL = `https://raw.githubusercontent.com/clouvelai/ardoise/${INSTALL_TAG}/install.sh`;
export const INSTALL_RELEASE_URL = `https://github.com/clouvelai/ardoise/releases/tag/${INSTALL_TAG}`;
export const INSTALL_ONE_LINER = `curl -fsSL ${INSTALL_SCRIPT_URL} | sh`;
export const INSTALL_VERIFY = [
  `curl -fsSL ${INSTALL_SCRIPT_URL} -o install.sh`,
  `echo "${INSTALL_SHA256}  install.sh" | shasum -a 256 -c -`,
  "chmod +x install.sh && ./install.sh",
].join("\n");
