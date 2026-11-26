public class newV {
    public static double snippet(int year) {
        int leap = 0;
        if ((year % 4 == 0 || year % 400 == 0) && year % 100 != 0) {
            leap = 1;
        }
        return leap;
    }
}
