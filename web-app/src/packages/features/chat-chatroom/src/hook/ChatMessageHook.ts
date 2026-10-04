import { useChatMessageStateHook } from "./useChatMessageStateHook";
import { useChatSendNormalHook } from "./useChatSendNormalHook";
import { useChatSendStreamHook } from "./useChatSendStreamHook";

/** 兼容旧用法 —— 组合所有子 hook 暴露统一接口 */
export function chatMessageHook() {
  const state = useChatMessageStateHook();
  const sendNormal = useChatSendNormalHook();
  const sendStream = useChatSendStreamHook();

  return {
    input: state.input,
    setInput: state.setInput,
    messages: state.messages,
    sending: state.sending,
    sendNormal: sendNormal.sendNormal,
    sendStream: sendStream.sendStream,
  };
}
