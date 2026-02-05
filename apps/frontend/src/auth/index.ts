export type AuthToken = {
  accessToken: string;
  tokenType: string;
};

export const emptyToken: AuthToken = {
  accessToken: "",
  tokenType: "bearer"
};
