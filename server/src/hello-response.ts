import { getHelloWorldMessage } from '../../backend/src/library/hello-world.js'

export type HelloMessageProvider = () => string

export function buildHelloPayload(getMessage: HelloMessageProvider = getHelloWorldMessage) {
  return {
    message: getMessage(),
  }
}
