// web-app/src/packages/biz-common/net-api/src/net-client.ts
import { BizHttp } from '@ming/biz-common-net';
import type { INetClient } from '@ming/biz-common-net';

// 内部保留原始实例引用，供 init 使用；对外只导出收窄类型
const bizHttpInstance = new BizHttp();
export const netClient = bizHttpInstance as INetClient;
export const _netClientImpl = bizHttpInstance;  // 仅供同包 init 使用，不对外导出