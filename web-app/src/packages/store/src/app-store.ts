import {
  create,
  type StateCreator,
  type StoreApi,
  type UseBoundStore,
} from "zustand";
//create(...) 返回一个 hook（useStore），组件用它读/写状态。
// StateCreator<T> 是 Zustand 的类型，表示"定义 store 的函数"
// UseBoundStore<StoreApi<T>> 是 Zustand 的返回值类型

// function add(a, b) {
//   return a + b;
// }
// add(1, 2);   // 3

// // 柯里化：一次传一个
// function curriedAdd(a) {
//   return function (b) {
//     return a + b;
//   };
// }
// curriedAdd(1)(2);   // 3
//         ↑ 第一次调用返回函数
//            ↑ 第二次调用返回结果

/** 项目级通用 store 工厂。业务状态和业务动作由调用方定义。 */
export const createAppStore = <T extends object>(
  initializer: StateCreator<T>,
): UseBoundStore<StoreApi<T>> => create<T>()(initializer);

export type AppStoreInitializer<T extends object> = StateCreator<T>;
