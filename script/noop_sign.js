// Custom no-op signing hook to bypass winCodeSign symlink issues on non-admin Windows machines
exports.default = async function (configuration) {
    console.log(`[Signing Hook] Bypassing code signing for: ${configuration.path}`);
    return true;
};
