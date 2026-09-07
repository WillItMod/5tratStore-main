// Extracted from getumbrel/umbrel tag 1.7.4, packages/umbreld/source/modules/apps/app.ts
// https://github.com/getumbrel/umbrel/blob/1.7.4/packages/umbreld/source/modules/apps/app.ts#L100-L138
// Original file SHA256: 1cca878945bc3f6e367952aa0904b07d905b73e284a9a578a7feeb42b0ff4a4a
// Keeps the actual container-name and volume migration statements. TypeScript
// non-null/type assertions are erased; unrelated GPU and file I/O are omitted.
function patchComposeFile(compose, id) {
  for (const serviceName of Object.keys(compose.services)) {
    if (!compose.services[serviceName].container_name) {
      compose.services[serviceName].container_name = `${id}_${serviceName}_1`;
    }
    compose.services[serviceName].volumes = compose.services[serviceName].volumes?.map((volume) => {
      return (volume)
        ?.replace('/data/storage/downloads', `/home/Downloads`)
        ?.replace('/data/storage', `/home`);
    });
  }
  return compose;
}

const fs = require('node:fs');
const {compose, id} = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(patchComposeFile(compose, id)));
