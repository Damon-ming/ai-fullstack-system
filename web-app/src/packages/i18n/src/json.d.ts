// 我只是在声明类型，不会生成任何实际的 JavaScript 代码。
// 编译后，所有 declare 语句都会被完全擦除，不产生任何 JS 代码。
// 这是在声明一个通配模块：任何以 .json 结尾的导入路径
declare module "*.json" {
  const value: Record<string, unknown>;
  // 该模块的默认导出是 value
  export default value;
}
