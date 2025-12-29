{pkgs ? import <nixpkgs> {}}:
pkgs.mkShell {
  buildInputs = [
    pkgs.just
    pkgs.ruff
    pkgs.ty
    pkgs.uv
  ];
}
