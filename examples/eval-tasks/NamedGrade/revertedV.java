public class revertedV {
    // naive rollback of the changed if: back to the magic number, the refactoring is lost
    public static double snippet(int score) {
        int pass = 60;
        int top = pass + 30;
        int g = 0;
        if (score >= pass) {
            g = 1;
        }
        if (score >= 90) {
            g = g + 1;
        }
        return g;
    }
}
