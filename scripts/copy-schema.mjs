import { cp, mkdir } from 'node:fs/promises';
await mkdir('dist/schemas', {recursive:true});
await cp('schemas/creative-job.v1.schema.json','dist/schemas/creative-job.v1.schema.json');
