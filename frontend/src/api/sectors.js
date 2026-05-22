import api from './index'

/** 获取板块轮动分析 */
export function getSectorRotation() {
  return api.get('/sectors/rotation')
}
