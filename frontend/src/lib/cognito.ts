// AWS Cognito 로그인 래퍼 — amazon-cognito-identity-js로 ID 토큰만 발급받는다(Hosted UI·소셜·MFA 미사용).
import {
  AuthenticationDetails,
  CognitoUser,
  CognitoUserPool,
} from 'amazon-cognito-identity-js';

// local(기본): 자체 /api/auth/login. cognito: Cognito User Pool 직접 인증.
export const AUTH_PROVIDER = process.env.NEXT_PUBLIC_AUTH_PROVIDER ?? 'local';

const USER_POOL_ID = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? '';
const CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? '';

let pool: CognitoUserPool | null = null;

function getPool(): CognitoUserPool {
  if (!USER_POOL_ID || !CLIENT_ID) {
    throw new Error('Cognito 설정(NEXT_PUBLIC_COGNITO_*)이 없습니다.');
  }
  if (!pool) pool = new CognitoUserPool({ UserPoolId: USER_POOL_ID, ClientId: CLIENT_ID });
  return pool;
}

// 로그인 → ID 토큰(JWT) 반환. username = 우리 login_id 규약(백엔드가 login_id로 DB User를 조회).
export function cognitoLogin(loginId: string, password: string): Promise<string> {
  const cognitoUser = new CognitoUser({ Username: loginId, Pool: getPool() });
  const authDetails = new AuthenticationDetails({ Username: loginId, Password: password });
  return new Promise<string>((resolve, reject) => {
    cognitoUser.authenticateUser(authDetails, {
      onSuccess: (session) => resolve(session.getIdToken().getJwtToken()),
      onFailure: (err) => reject(err instanceof Error ? err : new Error(String(err))),
      // 임시 비밀번호(관리자 발급) 상태 — 자가 재설정 흐름은 없으므로 안내만.
      newPasswordRequired: () =>
        reject(new Error('비밀번호 재설정이 필요합니다. 관리자에게 문의하세요.')),
    });
  });
}

// 로그아웃 시 Cognito 로컬 세션(localStorage) 정리. 우리 토큰은 authApi가 별도 관리한다.
export function cognitoSignOut(): void {
  if (AUTH_PROVIDER !== 'cognito') return;
  try {
    getPool().getCurrentUser()?.signOut();
  } catch {
    // 설정 없음·세션 없음 — 무시.
  }
}
