public class newV {
    // divide each term first to avoid overflow: loses the remainders
    public static double snippet(int a, int b, int c) {
        int avg = 0;
        avg = a / 3 + b / 3 + c / 3;
        return avg;
    }
}
